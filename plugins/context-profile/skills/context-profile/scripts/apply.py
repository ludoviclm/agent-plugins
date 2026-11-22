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
RESERVED = ("global", "except", "reset")


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
    """Return the requested profile names from the request words."""
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
        lines.append("  reset: remove the profile entries, user settings apply again")
        fail(3, "\n".join(lines))
    excluded.discard("basic")  # `except` never excludes basic
    if "basic" in profiles:
        requested.add("basic")
    return requested - excluded


def managed(profiles):
    """The only entries this script writes: listed plugins (but its own) and listed tools."""
    plugins = {i for p in profiles.values() for i in p.get("plugins", [])
               if not i.startswith(SELF_PLUGIN)}
    tools = {t for p in profiles.values() for t in p.get("tools", [])}
    return plugins, tools


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


def effective(project):
    """Merge user, project and local settings the way Claude Code does: the later scope wins
    for a plugin, deny rules add up. Without it, a folder with no local file reads as basic
    while the user settings may turn everything on."""
    enabled, deny = {}, set()
    for path in (CLAUDE_HOME / "settings.json",
                 project / ".claude" / "settings.json",
                 project / ".claude" / "settings.local.json"):
        try:
            s = load_json(path)
        except ValueError as e:
            fail(2, f"Invalid JSON in {path}: {e}")
        enabled.update(s.get("enabledPlugins", {}))
        deny |= set(s.get("permissions", {}).get("deny", []))
    return enabled, deny


def short(plugin_id):
    return plugin_id.split("@", 1)[0]


def status_label(profiles, project, local):
    """One line: 'basic + web', 'basic + pbi (partial 3/8)', 'global', with notes."""
    enabled, deny = effective(project)
    installed = installed_ids(project)
    parts, missing_all, all_full = ["basic"], [], True
    for name, p in profiles.items():
        plugins = [i for i in p.get("plugins", []) if not i.startswith(SELF_PLUGIN)]
        tools = p.get("tools", [])
        if name == "basic" or not (plugins or tools):
            continue
        on = sum(enabled.get(i) is True for i in plugins) + sum(t not in deny for t in tools)
        total = len(plugins) + len(tools)
        if on < total:
            all_full = False
        if on == 0:
            continue
        label = name if on == total else f"{name} (partial {on}/{total})"
        missing = [short(i) for i in plugins if enabled.get(i) is True and i not in installed]
        if missing:
            label += f" (not installed: {', '.join(missing)})"
            missing_all += missing
        parts.append(label)
    if all_full:
        label = "global"
        if missing_all:
            label += f" (not installed: {', '.join(sorted(set(missing_all)))})"
    else:
        label = " + ".join(parts)

    plugins, tools = managed(profiles)
    if not (set(local.get("enabledPlugins", {})) & plugins
            or set(local.get("permissions", {}).get("deny", [])) & tools):
        label += " (no profile set in this folder: user settings apply)"
    return label


def hook(config_path):
    """SessionStart hook: silent without a configuration, never blocks the session."""
    try:
        cwd = json.load(sys.stdin).get("cwd") or os.getcwd()
    except ValueError:
        cwd = os.getcwd()
    try:
        config = load_json(config_path)
        profiles = config.get("profiles")
        if not profiles:
            return
        project = Path(cwd).resolve()
        local = load_json(project / ".claude" / "settings.local.json")
        msg = f"Context profile: {status_label(profiles, project, local)}"
    except (ValueError, SystemExit) as e:
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
        config = load_json(args.config, required=True)
    except FileNotFoundError:
        fail(2, f"No configuration file at {args.config}. Create it from profiles.example.json.")
    except ValueError as e:
        fail(2, f"Invalid JSON in {args.config}: {e}")
    profiles = config.get("profiles", {})
    if not profiles:
        fail(2, f"No profiles in {args.config}.")
    clash = sorted(set(profiles) & set(RESERVED))
    if clash:
        fail(2, f"Reserved word used as a profile name in {args.config}: {', '.join(clash)}.")

    project = Path(args.project).resolve()
    target = project / ".claude" / "settings.local.json"
    try:
        settings = load_json(target)
    except ValueError as e:
        fail(2, f"Invalid JSON in {target}, left untouched: {e}")

    if args.status or not args.profiles:
        print("Profile: " + status_label(profiles, project, settings))
        return

    words = [w.lower() for w in args.profiles]
    reset = "reset" in words
    if reset and len(words) > 1:
        fail(3, "reset takes no profile name: run it alone.")
    active = set() if reset else resolve(profiles, args.profiles)

    managed_plugins, managed_tools = managed(profiles)
    on = {i for n in active for i in profiles[n].get("plugins", [])} & managed_plugins
    allowed = {t for n in active for t in profiles[n].get("tools", [])}

    enabled = settings.setdefault("enabledPlugins", {})
    permissions = settings.setdefault("permissions", {})
    deny = [r for r in permissions.get("deny", []) if r not in managed_tools]
    if reset:
        # Drop the managed entries instead of writing them: the other scopes decide again.
        for plugin_id in managed_plugins:
            enabled.pop(plugin_id, None)
    else:
        for plugin_id in sorted(managed_plugins):
            enabled[plugin_id] = plugin_id in on
        deny += sorted(managed_tools - allowed)
    permissions["deny"] = deny
    # Remove the containers a reset left empty, then the file itself if nothing is left.
    for key, parent in (("deny", permissions), ("enabledPlugins", settings)):
        if not parent[key]:
            del parent[key]
    if not permissions:
        del settings["permissions"]

    if not args.dry_run:
        if settings:
            target.parent.mkdir(parents=True, exist_ok=True)
            with open(target, "w", encoding="utf-8", newline="\n") as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
                f.write("\n")
        elif target.exists():
            target.unlink()

    dry = "  (dry run, nothing written)" if args.dry_run else ""
    if reset:
        print(f"Reset: profile entries removed, user settings apply.{dry}")
        print(f"File: {target}" + ("" if settings else " (deleted: nothing else in it)"))
        print("Applies to the next session opened on this folder.")
        return

    print(f"Profiles: {', '.join(sorted(active))}{dry}")
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
