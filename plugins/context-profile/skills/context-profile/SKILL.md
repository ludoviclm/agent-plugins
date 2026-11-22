---
name: context-profile
description: Switches the context profile of the current Claude Code project - which plugins are enabled and which heavy tools are denied - by writing `.claude/settings.local.json`, so the next session loads only what the work needs, and installs a profile's missing plugins once the user agrees. Also measures how much of the skill listing budget each plugin takes. Invoke when the user asks to switch, combine, show or create a profile ("switch to the web profile", "enable pbi and databricks", "global except design", "which profile is active?"), to load or unload a plugin for this project only, or asks why skills lose their descriptions or which plugins are the heaviest.
---

# Context profiles

A profile is a named set of plugins (and optionally tools) to load in a project. This skill
writes one settings file and says when it takes effect. When a profile names a plugin that is
not installed, it offers to install it, and installs only after the user agrees.

## The configuration

Profiles live in `~/.claude/context-profiles.json`, owned by the user:

```json
{
  "marketplaces": {
    "claude-plugins-official": "anthropics/claude-plugins-official"
  },
  "profiles": {
    "basic": { "description": "Always on", "plugins": [], "tools": [] },
    "web":   { "description": "Static websites", "plugins": ["frontend-design@claude-plugins-official"] },
    "docs":  { "description": "Writing sessions", "tools": ["Artifact"] }
  }
}
```

- `marketplaces`: for each marketplace name used in a plugin id, the source to pass to
  `claude plugin marketplace add` (a GitHub `owner/repo`, a Git URL or a local path).
  Optional: only needed to install missing plugins.
- `plugins`: plugin ids (`<plugin>@<marketplace>`) the profile turns on.
- `tools`: permission rule names the profile allows, for heavy tools: a built-in tool
  (`Artifact`), or `mcp__<server>` for every tool of an MCP server. When no active profile
  lists a tool, it is denied, which removes it from the context.
- `basic`, if defined, is **always included**.
- `global` is reserved: it turns on every managed plugin and allows every managed tool.

**No configuration file**: offer to create it. Start from `profiles.example.json` next to
this file, ask which profiles the user wants, and say which of their plugins are not
installed yet (they will be offered at the first switch) before writing.

**Managed entries** - the only ones this skill writes:
- plugins: every id listed in at least one profile;
- deny rules: every name listed in the `tools` of at least one profile.

Anything else - another plugin, another deny rule, any other key - is left untouched.
🚫 Never write the entry of the plugin that ships this skill, nor of a plugin the user does not
list: a guardrail plugin must stay out of reach of a profile switch.

## Requesting profiles

- Profiles are cumulative: `pbi docs` loads the union of both, plus `basic`.
- `global except design` (or `global except <p> <p>...`) turns everything on, except what the
  excluded profiles turn on. `except` only follows `global` and never excludes `basic`.

## Applying a profile

1. **Check the names** against the configuration. An unknown profile: stop, list the valid
   ones with their description, write nothing.
2. **Missing plugins.** Compare the plugins the request turns on with `claude plugin list`.
   For each missing one, check that its marketplace is known (`claude plugin marketplace
   list`); if not, take its source from `marketplaces`, or ask the user for it. Show the list
   - plugin, marketplace, source - and **ask once for approval: installing runs third-party
   code**. On approval, from the session's folder:
   - `claude plugin marketplace add <source>` for each unknown marketplace;
   - `claude plugin install <plugin>@<marketplace> --scope local` for each plugin. The local
     scope installs it for this folder only: the user scope would turn it on everywhere,
     which defeats the profiles.

   Refused, or an install fails: carry on, the plugin stays listed as missing in step 7.
3. **Target file**: `.claude/settings.local.json` of the session's primary working directory,
   the folder the session was opened on. Never another folder: Claude Code does not load the
   settings of additional directories. Claude Code normally keeps this file out of Git.
4. **Read the file if it exists, and keep every key this skill does not manage.** Read it
   after step 2: an install writes its own entry there.
5. For each managed plugin, set `enabledPlugins.<id>` to `true` if an active profile turns it
   on (and, after `global except`, no excluded profile does), `false` otherwise.
6. In `permissions.deny`, remove every managed tool, then add back each one no active profile
   allows. Leave every other rule in place.
7. **Warn** about any plugin set to `true` that is still not installed: it will not load.
8. Write the file - Claude Code asks the user to approve any write to its settings files,
   which is expected: if the write is refused, show the content to paste instead. Then show
   the resulting `enabledPlugins` and `permissions.deny`, and say: **the profile applies to
   the next session opened on this folder**; the current one keeps what it loaded.
   `/context` in the new session shows the result.

**No profile named** ("which profile is active?"): read the file and report the profiles whose
plugins are all `true`, and the managed tools denied. No file means the user settings apply
everywhere.

## Measuring the skill listing

Run `scripts/measure.py`, next to this file, with its absolute path:

```bash
python <skill-dir>/scripts/measure.py --project <primary working directory>
```

It lists, for each installed plugin and skill folder, the number of skills, the characters
their names and descriptions take in the listing, and whether they are enabled for this
project, then compares the enabled total to the listing budget. Python 3.8+ standard library
only. No Python: say so, and point to `/context`, which remains the reference.

## What a profile cannot do

- **Hide a single skill of a plugin.** The granularity is the plugin. `/skills` hides
  personal and project skills one by one, not plugin skills.
- **Save many tokens by cutting skills.** Above its budget, Claude Code drops descriptions;
  cutting a plugin mostly gives descriptions back to the other skills, so Claude picks the
  right one more often. The large savings are heavy tools and MCP servers (`tools`).
- **Give two parallel sessions of the same folder two profiles at start.** They read the same
  file: open the second one after switching.

**Why not the user scope** (`~/.claude/settings.json`): it switches every session on the
machine. A project file keeps each folder on its own profile.
