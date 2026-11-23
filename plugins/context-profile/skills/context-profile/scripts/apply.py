#!/usr/bin/env python3
"""Apply Claude Code context profiles to a project's .claude/settings.local.json.

Usage:
  apply.py web                      apply basic + web
  apply.py pbi docs                 profiles stack
  apply.py global except design     everything but design
  apply.py reset                    remove the profile entries: user settings apply again
  apply.py --status                 report the active profiles, write nothing
  apply.py web --dry-run            show the result, write nothing
  apply.py --hook                   SessionStart hook: report the profile of the session

Only the plugins, tools and skills listed in the profiles are written; every other setting is kept.
Profile names are case-insensitive. Standard library only.
Exit codes: 0 ok, 2 configuration problem, 3 unknown profile.
"""

import argparse
import json
import os
import sys
from pathlib import Path

CLAUDE_HOME = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
CONFIG = CLAUDE_HOME / "context-profiles.json"
# The plugin that ships this skill: never switched by a profile.
SELF_PLUGIN = "context-profile@"
RESERVED = ("global", "except", "reset")
APPLIES = ("Plugins, skills and denied tools apply when the session restarts: reload the window (VS Code)"
           " or run `claude --continue` to keep the conversation. An allowed tool may appear right away.")


class ConfigError(Exception):
    """A problem to report: main() prints it with its exit code, the hook in its banner."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def fail(code, message):
    raise ConfigError(code, message)


def load_json(path, required=False):
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            raise
        return {}
    except ValueError as e:
        fail(2, f"Invalid JSON in {path}: {e}")


def load_profiles(config, config_path):
    """Profiles keyed by lowercase name, so that `Web` and `web` are the same profile."""
    profiles = {}
    for name, profile in (config.get("profiles") or {}).items():
        key = name.lower()
        if key in profiles:
            fail(2, f"Two profiles named {key} (case-insensitive) in {config_path}.")
        profiles[key] = profile
    if not profiles:
        fail(2, f"No profiles in {config_path}.")
    clash = sorted(set(profiles) & set(RESERVED))
    if clash:
        fail(2, f"Reserved word used as a profile name in {config_path}: {', '.join(clash)}.")
    return profiles


def resolve(profiles, words):
    """Return the requested profile names from the normalized request words."""
    requested, excluded = set(), set()
    if "global" in words:
        requested = set(profiles)
        if "except" in words:
            excluded = set(words[words.index("except") + 1:])
        words = [w for w in words if w not in ("global", "except") and w not in excluded]
    requested |= set(words)
    unknown = sorted((requested | excluded) - set(profiles))
    if unknown:
        lines = [f"Unknown profile: {', '.join(unknown)}. Valid profiles:"]
        lines += [f"  {n}: {p.get('description', '')}" for n, p in profiles.items()]
        lines.append("  global: everything (global except <profile>... to leave some out)")
        lines.append("  reset: remove the profile entries, user settings apply again")
        fail(3, "\n".join(lines))
    excluded.discard("basic")  # `except` never excludes basic
    if "basic" in profiles:
        requested.add("basic")
    return requested - excluded


def managed(profiles):
    """The only entries this script writes: listed plugins (but its own), tools and skills."""
    plugins = {i for p in profiles.values() for i in p.get("plugins", [])
               if not i.startswith(SELF_PLUGIN)}
    tools = {t for p in profiles.values() for t in p.get("tools", [])}
    skills = {s for p in profiles.values() for s in p.get("skills", [])}
    return plugins, tools, skills


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def installed_ids(project):
    """Plugin ids installed for this project: user scope, or local/project scope here."""
    registry = load_json(CLAUDE_HOME / "plugins" / "installed_plugins.json").get("plugins", {})
    ids = set()
    for plugin_id, entries in registry.items():
        for e in entries:
            path = e.get("projectPath")
            if e.get("scope") == "user" or (path and same_path(path, project)):
                ids.add(plugin_id)
    return ids


def effective(project):
    """Merge user, project and local settings the way Claude Code does: the later scope wins
    for a plugin, deny rules add up. Without it, a folder with no local file reads as basic
    while the user settings may turn everything on."""
    enabled, deny, skills = {}, set(), {}
    for path in (CLAUDE_HOME / "settings.json",
                 project / ".claude" / "settings.json",
                 project / ".claude" / "settings.local.json"):
        s = load_json(path)
        enabled.update(s.get("enabledPlugins", {}))
        deny |= set(s.get("permissions", {}).get("deny", []))
        # skillOverrides merge like plugins: a local "on" beats a user "off" (tested 2.1.302).
        skills.update(s.get("skillOverrides", {}))
    return enabled, deny, skills


def short(plugin_id):
    return plugin_id.split("@", 1)[0]


def status_label(profiles, project, local):
    """One line: 'basic + web', 'basic + pbi (partial 3/8)', 'global', with notes."""
    enabled, deny, overrides = effective(project)
    installed = installed_ids(project)

    def items(p):
        """A profile's entries as (kind, name) pairs, so a tool and a skill never collide."""
        return ([("plugin", i) for i in p.get("plugins", []) if not i.startswith(SELF_PLUGIN)]
                + [("tool", t) for t in p.get("tools", [])]
                + [("skill", s) for s in p.get("skills", [])])

    def is_on(item):
        kind, name = item
        if kind == "plugin":
            return enabled.get(name) is True
        return name not in deny if kind == "tool" else overrides.get(name) != "off"

    entries = {n: items(p) for n, p in profiles.items() if n != "basic" and items(p)}
    full = {n for n, its in entries.items() if all(map(is_on, its))}
    # An entry shared with a profile that is fully on proves nothing about this one:
    # pdf in both pbi and docs must not show docs as partial when only pbi is on.
    covered = {i for n in full for i in entries[n]}
    parts, missing_all = ["basic"], []
    for name, its in entries.items():
        if name not in full:
            its = [i for i in its if i not in covered]
        on = sum(map(is_on, its))
        if on == 0 and name not in full:
            continue
        label = name if name in full else f"{name} (partial {on}/{len(its)})"
        missing = [short(i) for k, i in its if k == "plugin" and enabled.get(i) is True
                   and i not in installed]
        if missing:
            label += f" (not installed: {', '.join(missing)})"
            missing_all += missing
        parts.append(label)
    if full == set(entries):
        label = "global"
        if missing_all:
            label += f" (not installed: {', '.join(sorted(set(missing_all)))})"
    else:
        label = " + ".join(parts)

    plugins, tools, skills = managed(profiles)
    if not (set(local.get("enabledPlugins", {})) & plugins
            or set(local.get("permissions", {}).get("deny", [])) & tools
            or set(local.get("skillOverrides", {})) & skills):
        label += " (no profile set in this folder: user settings apply)"
    return label


def hook(config_path):
    """SessionStart hook: silent without a configuration, never blocks the session."""
    try:
        # Read bytes: the hook input is UTF-8, and the console code page (cp1252 on Windows)
        # would garble an accented folder name and report the profile of another folder.
        cwd = json.load(sys.stdin.buffer).get("cwd") or os.getcwd()
    except (ValueError, AttributeError):
        cwd = os.getcwd()
    try:
        config = load_json(config_path)
        if not config.get("profiles"):
            return
        profiles = load_profiles(config, config_path)
        project = Path(cwd).resolve()
        local = load_json(project / ".claude" / "settings.local.json")
        msg = f"Context profile: {status_label(profiles, project, local)}"
    except (ConfigError, OSError) as e:
        print(json.dumps({"systemMessage": f"Context profile: unknown ({e})"}))
        return
    context = msg + "."
    # Some clients (IDE extensions) record systemMessage without showing it: `announce` asks
    # Claude to say the profile in its first reply instead.
    if config.get("announce"):
        context += (" Start your first reply of this session with one line giving this"
                    " profile, then answer normally.")
    print(json.dumps({
        "systemMessage": msg,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context},
    }))


def write_atomic(target, settings):
    """Write through a temporary file: an interrupted write never truncates the settings."""
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, target)


def run(args):
    try:
        config = load_json(args.config, required=True)
    except FileNotFoundError:
        fail(2, f"No configuration file at {args.config}. Create it from profiles.example.json.")
    profiles = load_profiles(config, args.config)

    project = Path(args.project).resolve()
    target = project / ".claude" / "settings.local.json"
    settings = load_json(target)

    if args.status or not args.profiles:
        print("Profile: " + status_label(profiles, project, settings))
        return

    # "pbi, docs" and "pbi docs" are the same request.
    words = [w.lower().strip(",") for w in args.profiles if w.strip(",")]
    reset = "reset" in words
    if reset and len(words) > 1:
        fail(3, "reset takes no profile name: run it alone.")
    active = set() if reset else resolve(profiles, words)

    managed_plugins, managed_tools, managed_skills = managed(profiles)
    on = {i for n in active for i in profiles[n].get("plugins", [])} & managed_plugins
    allowed = {t for n in active for t in profiles[n].get("tools", [])}
    skills_on = {s for n in active for s in profiles[n].get("skills", [])}

    enabled = settings.setdefault("enabledPlugins", {})
    overrides = settings.setdefault("skillOverrides", {})
    permissions = settings.setdefault("permissions", {})
    deny = [r for r in permissions.get("deny", []) if r not in managed_tools]
    if reset:
        # Drop the managed entries instead of writing them: the other scopes decide again.
        for plugin_id in managed_plugins:
            enabled.pop(plugin_id, None)
        for skill in managed_skills:
            overrides.pop(skill, None)
    else:
        for plugin_id in sorted(managed_plugins):
            enabled[plugin_id] = plugin_id in on
        # "on" is written, not just "off" removed: it overrides an "off" of the user settings.
        for skill in sorted(managed_skills):
            overrides[skill] = "on" if skill in skills_on else "off"
        deny += sorted(managed_tools - allowed)
    permissions["deny"] = deny
    # Remove the containers a reset left empty, then the file itself if nothing is left.
    for key, parent in (("deny", permissions), ("enabledPlugins", settings),
                        ("skillOverrides", settings)):
        if not parent[key]:
            del parent[key]
    if not permissions:
        del settings["permissions"]

    if not args.dry_run:
        if settings:
            write_atomic(target, settings)
        elif target.exists():
            target.unlink()

    dry = "  (dry run, nothing written)" if args.dry_run else ""
    if reset:
        print(f"Reset: profile entries removed, user settings apply.{dry}")
        print(f"File: {target}" + ("" if settings else " (deleted: nothing else in it)"))
        print(APPLIES)
        return

    print(f"Profiles: {', '.join(sorted(active))}{dry}")
    print(f"File: {target}")
    print(f"On:  {', '.join(sorted(on)) or '-'}")
    print(f"Off: {', '.join(sorted(managed_plugins - on)) or '-'}")
    print(f"Denied tools: {', '.join(sorted(managed_tools - allowed)) or '-'}")
    if managed_skills:
        print(f"Skills on:  {', '.join(sorted(skills_on & managed_skills)) or '-'}")
        print(f"Skills off: {', '.join(sorted(managed_skills - skills_on)) or '-'}")

    missing = sorted(on - installed_ids(project))
    if missing:
        known = set(load_json(CLAUDE_HOME / "plugins" / "known_marketplaces.json"))
        sources = config.get("marketplaces", {})
        print("Not installed (will not load until installed):")
        for plugin_id in missing:
            market = plugin_id.split("@", 1)[-1]
            where = "known marketplace" if market in known else f"add: {sources.get(market, 'source unknown')}"
            print(f"  {plugin_id}  ({where})")
    print(APPLIES)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profiles", nargs="*", help="profile names, global except <names>, or reset")
    parser.add_argument("--project", default=os.getcwd(), help="session folder (default: current)")
    parser.add_argument("--config", default=str(CONFIG), help="profiles file")
    parser.add_argument("--status", action="store_true", help="report the active profiles")
    parser.add_argument("--dry-run", action="store_true", help="show the result, write nothing")
    parser.add_argument("--hook", action="store_true", help="run as a SessionStart hook")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.hook:
        hook(args.config)
        return
    try:
        run(args)
    except ConfigError as e:
        print(e)
        sys.exit(e.code)


if __name__ == "__main__":
    main()
