#!/usr/bin/env python3
"""Apply Claude Code context profiles to a project's .claude/settings.local.json.

Usage:
  apply.py web                      apply basic + web
  apply.py pbi docs                 profiles stack
  apply.py global except design     everything but design
  apply.py --status                 report the active profiles, write nothing
  apply.py web --dry-run            show the result, write nothing

Only the plugins and tools listed in the profiles are written; every other setting is kept.
Standard library only. Exit codes: 0 ok, 2 configuration problem, 3 unknown profile.
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


def load_json(path, required=False):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        if required:
            raise
        return {}


def fail(code, message):
    print(message)
    sys.exit(code)


def resolve(profiles, words):
    """Return (requested names, excluded names) from the request words."""
    words = [w.lower().strip(",") for w in words if w.strip(",")]
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
        fail(3, "\n".join(lines))
    excluded.discard("basic")  # `except` never excludes basic
    if "basic" in profiles:
        requested.add("basic")
    return requested - excluded, excluded


def installed_ids(project):
    """Plugin ids installed for this project: user scope, or local/project scope here."""
    registry = load_json(CLAUDE_HOME / "plugins" / "installed_plugins.json").get("plugins", {})
    here = os.path.normcase(str(project))
    ids = set()
    for plugin_id, entries in registry.items():
        for e in entries:
            path = e.get("projectPath")
            if e.get("scope") == "user" or (
                path and os.path.normcase(os.path.abspath(path)) == here
            ):
                ids.add(plugin_id)
    return ids


def status(profiles, settings):
    enabled = settings.get("enabledPlugins", {})
    deny = set(settings.get("permissions", {}).get("deny", []))
    active = [
        name for name, p in profiles.items()
        if name != "basic" and (p.get("plugins") or p.get("tools"))
        and all(enabled.get(i) is True for i in p.get("plugins", []))
        and not deny & set(p.get("tools", []))
    ]
    print("Active profiles: " + ", ".join(["basic"] + active) if active else "Active profile: basic")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("profiles", nargs="*", help="profile names, or: global except <names>")
    parser.add_argument("--project", default=os.getcwd(), help="session folder (default: current)")
    parser.add_argument("--config", default=str(CONFIG), help="profiles file")
    parser.add_argument("--status", action="store_true", help="report the active profiles")
    parser.add_argument("--dry-run", action="store_true", help="show the result, write nothing")
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    try:
        config = load_json(args.config, required=True)
    except FileNotFoundError:
        fail(2, f"No configuration file at {args.config}. Create it from profiles.example.json.")
    except ValueError as e:
        fail(2, f"Invalid JSON in {args.config}: {e}")
    profiles = config.get("profiles", {})
    if not profiles:
        fail(2, f"No profiles in {args.config}.")

    project = Path(args.project).resolve()
    target = project / ".claude" / "settings.local.json"
    try:
        settings = load_json(target)
    except ValueError as e:
        fail(2, f"Invalid JSON in {target}, left untouched: {e}")

    if args.status or not args.profiles:
        status(profiles, settings)
        return

    active, _ = resolve(profiles, args.profiles)

    managed_plugins = {i for p in profiles.values() for i in p.get("plugins", [])
                       if not i.startswith(SELF_PLUGIN)}
    managed_tools = {t for p in profiles.values() for t in p.get("tools", [])}
    on = {i for n in active for i in profiles[n].get("plugins", [])} & managed_plugins
    allowed = {t for n in active for t in profiles[n].get("tools", [])}

    enabled = settings.setdefault("enabledPlugins", {})
    for plugin_id in sorted(managed_plugins):
        enabled[plugin_id] = plugin_id in on
    permissions = settings.setdefault("permissions", {})
    deny = [r for r in permissions.get("deny", []) if r not in managed_tools]
    deny += sorted(managed_tools - allowed)
    permissions["deny"] = deny

    if not args.dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
            f.write("\n")

    print(f"Profiles: {', '.join(sorted(active))}" + ("  (dry run, nothing written)" if args.dry_run else ""))
    print(f"File: {target}")
    print(f"On:  {', '.join(sorted(on)) or '-'}")
    print(f"Off: {', '.join(sorted(managed_plugins - on)) or '-'}")
    print(f"Denied tools: {', '.join(sorted(managed_tools - allowed)) or '-'}")

    missing = sorted(on - installed_ids(project))
    if missing:
        known = set(load_json(CLAUDE_HOME / "plugins" / "known_marketplaces.json"))
        sources = config.get("marketplaces", {})
        print("Not installed (will not load until installed):")
        for plugin_id in missing:
            market = plugin_id.split("@", 1)[-1]
            where = "known marketplace" if market in known else f"add: {sources.get(market, 'source unknown')}"
            print(f"  {plugin_id}  ({where})")
    print("Applies to the next session opened on this folder.")


if __name__ == "__main__":
    main()
