#!/usr/bin/env python3
"""Measure how much of the Claude Code skill listing each plugin and skill folder takes.

Counts, per source, the skills found (SKILL.md files) and the characters their name and
description add to the listing Claude Code sends at session start. Standard library only.

The figures are an estimate: Claude Code also lists built-in skills, and its exact budget
depends on the version and the model's context window. `/context` remains the reference.
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))

# Observed ceiling of the listing on Claude Code 2.1.302 (2026-11-03); reportedly 1% of
# the context window by default, tunable with the `skillListingBudgetFraction` setting.
DEFAULT_BUDGET = 30000
# Reported per-description cap (`skillListingMaxDescChars`).
DEFAULT_MAX_DESC = 1536


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def frontmatter_field(text, key):
    """Return a top-level scalar of the YAML frontmatter, without a YAML parser.

    Handles plain, quoted and block (| or >) scalars, which covers SKILL.md files.
    """
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if not m:
        return ""
    lines = m.group(1).splitlines()
    for i, line in enumerate(lines):
        km = re.match(rf"{re.escape(key)}:\s*(.*)$", line)
        if not km:
            continue
        value = km.group(1).strip()
        if value[:1] in ("|", ">"):
            # Block scalar: the value is the following indented lines.
            block = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and not nxt[:1].isspace():
                    break
                block.append(nxt.strip())
            return " ".join(b for b in block if b)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        else:
            # Plain scalar continued on indented lines.
            for nxt in lines[i + 1:]:
                if not nxt[:1].isspace() or not nxt.strip():
                    break
                value += " " + nxt.strip()
        return value
    return ""


def measure_folder(root, max_desc, prefix=""):
    """Return (skill count, listing characters) for every SKILL.md under root.

    `prefix` is what the listing puts before each name: `<plugin>:` for a plugin skill.
    """
    count = chars = 0
    for skill in Path(root).rglob("SKILL.md"):
        # Skip trash and staging folders (.trash, .staging): Claude Code does not load them.
        if any(part.startswith(".") for part in skill.relative_to(root).parts):
            continue
        try:
            # utf-8-sig: a byte order mark would hide the frontmatter.
            text = skill.read_text(encoding="utf-8-sig")
        except OSError:
            continue
        name = frontmatter_field(text, "name") or skill.parent.name
        desc = frontmatter_field(text, "description")
        count += 1
        chars += len(prefix) + len(name) + min(len(desc), max_desc)
    return count, chars


def enabled_plugins(project):
    """Merge enabledPlugins from user, project and local settings; later scopes win."""
    merged = {}
    for path in (
        CLAUDE_HOME / "settings.json",
        project / ".claude" / "settings.json",
        project / ".claude" / "settings.local.json",
    ):
        merged.update(load_json(path).get("enabledPlugins", {}) or {})
    return merged


def install_path(entries, project):
    """Pick the install entry that applies to this project: local, then project, then user."""
    def same(p):
        return p and os.path.normcase(os.path.abspath(p)) == os.path.normcase(str(project))

    for scope in ("local", "project"):
        for e in entries:
            if e.get("scope") == scope and same(e.get("projectPath")):
                return e.get("installPath")
    for e in entries:
        if e.get("scope") == "user":
            return e.get("installPath")
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--project", default=os.getcwd(), help="session folder (default: current)")
    parser.add_argument("--budget", type=int, default=DEFAULT_BUDGET, help="listing budget in characters")
    parser.add_argument("--max-desc", type=int, default=DEFAULT_MAX_DESC, help="per-description cap")
    args = parser.parse_args()
    if args.budget <= 0 or args.max_desc <= 0:
        parser.error("--budget and --max-desc must be positive")

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    project = Path(args.project).resolve()
    enabled = enabled_plugins(project)
    installed = load_json(CLAUDE_HOME / "plugins" / "installed_plugins.json").get("plugins", {})

    rows = []  # (source, on, skills, chars)
    for plugin_id, entries in installed.items():
        path = install_path(entries, project)
        if not path or not Path(path).is_dir():
            continue
        skills, chars = measure_folder(path, args.max_desc, plugin_id.split("@", 1)[0] + ":")
        if skills:
            rows.append((plugin_id, enabled.get(plugin_id) is True, skills, chars))

    # Skills synced from claude.ai live in one bucket per account under skills/synced.
    synced = CLAUDE_HOME / "skills" / "synced"
    folders = [("project skills (.claude/skills)", project / ".claude" / "skills", True)]
    personal = CLAUDE_HOME / "skills"
    if personal.is_dir():
        folders += [(f"personal skill {d.name}", d, True) for d in personal.iterdir()
                    if d.is_dir() and d != synced and not d.name.startswith(".")]
    if synced.is_dir():
        folders += [(f"claude.ai synced skills ({d.name[:8]})", d, None) for d in synced.iterdir()
                    if d.is_dir() and not d.name.startswith(".")]
    for label, folder, on in folders:
        if folder.is_dir():
            skills, chars = measure_folder(folder, args.max_desc)
            if skills:
                rows.append((label, on, skills, chars))

    rows.sort(key=lambda r: r[3], reverse=True)
    width = max([len(r[0]) for r in rows] + [6])
    print(f"Project: {project}\n")
    print(f"{'Source':<{width}}  {'On':<3}  {'Skills':>6}  {'Chars':>7}  {'Budget':>6}")
    for source, on, skills, chars in rows:
        share = 100 * chars / args.budget
        flag = "?" if on is None else ("yes" if on else "no")
        print(f"{source:<{width}}  {flag:<3}  {skills:>6}  {chars:>7,}  {share:>5.0f}%")

    on_skills = sum(r[2] for r in rows if r[1])
    on_chars = sum(r[3] for r in rows if r[1])
    print(f"\nEnabled: {on_skills} skills, {on_chars:,} characters, "
          f"{100 * on_chars / args.budget:.0f}% of a {args.budget:,}-character budget.")
    if on_chars > args.budget:
        print("Over budget: Claude Code will drop descriptions. Switch to a lighter profile.")
    if any(r[1] is None for r in rows):
        print("Synced claude.ai skills (?) are not in the total: only the signed-in account's bucket loads.")
    print("Built-in skills are not counted. /context shows the actual listing.")


if __name__ == "__main__":
    main()
