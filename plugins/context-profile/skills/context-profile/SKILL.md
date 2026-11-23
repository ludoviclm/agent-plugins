---
name: context-profile
description: Switches this project's context profile (enabled plugins, skills, denied heavy tools) and measures each plugin's weight in the skill listing. Invoke to switch, combine, reset, show or create a profile ("switch to the web profile", "global except design", "which profile is active?"), to load or unload a plugin for this project only, or when skills lose their descriptions.
---

# Context profiles

A profile is a named set of plugins (and optionally tools and skills) to load in a project. This skill
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
    "docs":  { "description": "Writing sessions", "tools": ["Artifact"], "skills": ["anthropic-skills:docx"] }
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
- `skills`: skill names the profile turns on, for skills that do not come from a plugin
  (synced from claude.ai, built-in, personal). When no active profile lists a skill, it is
  turned off, which removes it from the listing. Use the full name: a synced skill is
  `anthropic-skills:<name>`, and a bare name targets a built-in skill of that name first.
  A plugin's skills follow their plugin: list the plugin instead.
- `basic`, if defined, is **always included**.
- `global` is reserved: it turns on every managed plugin and skill, and allows every managed tool.
- Profile names are case-insensitive: `Web` and `web` are the same profile.

**No configuration file**: offer to create it. Start from `profiles.example.json` next to
this file, ask which profiles the user wants, and say which of their plugins are not
installed yet (they will be offered at the first switch) before writing.

**Managed entries** - the only ones this skill writes:
- plugins: every id listed in at least one profile;
- deny rules: every name listed in the `tools` of at least one profile;
- skill overrides: every name listed in the `skills` of at least one profile.

Anything else - another plugin, another deny rule, any other key - is left untouched.
🚫 Never write the entry of the plugin that ships this skill, nor of a plugin the user does not
list: a guardrail plugin must stay out of reach of a profile switch.

## Requesting profiles

- Profiles are cumulative: `pbi docs` loads the union of both, plus `basic`.
- `reset` removes the managed entries from the folder's file, alone, never with a profile
  name: the user settings apply again. The file is deleted if nothing else is left in it.
- `global except design` (or `global except <p> <p>...`) loads every profile but the excluded
  ones. `except` only follows `global` and never excludes `basic`.

## Applying a profile

**Run `scripts/apply.py` in one call, and nothing before it** - no reading of the
configuration or the settings first: the script does the whole job, fast.

```bash
python3 <skill-dir>/scripts/apply.py <profiles> --project <primary working directory>
```

Use `python` where `python3` is missing (often on Windows), for both scripts.

- `<profiles>`: the user's words as profile names, e.g. `web`, `pbi docs`,
  `global except design`.
- `--project`: the session's primary working directory, the folder the session was opened
  on. Never another folder: Claude Code does not load the settings of additional directories.
- `--status` instead of profiles: reports the active profiles ("which profile is active?"),
  from the user, project and local settings merged. It flags a partial profile
  (`pbi (partial 7/8)`), a plugin on but not installed, `global` when every profile is on, and
  a folder with no profile of its own.
- `--dry-run`: shows the result without writing ("what would the web profile change?").

The script writes `enabledPlugins`, `skillOverrides` and `permissions.deny` in
`.claude/settings.local.json`, for the plugins, skills and tools listed in the profiles only, keeps every other key, never touches
the plugin that ships this skill, and prints a summary. Exit code 3: unknown profile, the
output lists the valid ones; exit code 2: configuration problem, the output says which.

**Then relay the summary briefly**, and say: **the plugins, skills and denied tools of the profile
apply when the session restarts on this folder**, and a restart keeps the conversation: in VS
Code, "Developer: Reload Window" resumes it; in a terminal, quit and run `claude --continue`.
Until then the session keeps the plugins and tools it loaded; only a newly allowed tool may
appear right away (Claude Code reloads permission rules during a session). `/context` after
the restart shows the result.

**Missing plugins** - the summary lists them under "Not installed", with their marketplace
when it is unknown. Ask once for approval, **installing runs third-party code**, then, from
the session's folder:
- `claude plugin marketplace add <source>` for each marketplace marked `add:`; when the source
  is unknown, ask the user for it;
- `claude plugin install <plugin>@<marketplace> --scope local` for each plugin. The local scope
  installs it for this folder only: the user scope would turn it on everywhere, which defeats
  the profiles. The install also enables it in the same file: no need to rerun the script.

Refused, or an install fails: say the plugin will not load until installed.

**No Python**: apply the same rules by hand. Read the configuration and
`.claude/settings.local.json`; set every plugin listed in a profile to `true` if an active
profile lists it, `false` otherwise (never the plugin that ships this skill); in
`permissions.deny`, remove every tool listed in a profile, then add back those no active
profile allows; in `skillOverrides`, set every skill listed in a profile to `"on"` if an
active profile lists it, `"off"` otherwise; keep every other key. For `reset`, remove those entries instead of writing
them. Claude Code asks the user to approve the write.

## The session banner

The plugin ships a `SessionStart` hook, `apply.py --hook`, that shows `Context profile: ...`
at the start of each session, from the same merge as `--status`. It is silent without a
configuration file. With `"announce": true` at the top level of the configuration, it also
asks Claude to state the profile in its first reply, for clients that do not display hook
messages. A banner in the context reflects the session start: for the current state of the
file, run `--status`.

## Measuring the skill listing

Run `scripts/measure.py`, next to this file, with its absolute path:

```bash
python3 <skill-dir>/scripts/measure.py --project <primary working directory>
```

It lists, for each installed plugin and skill folder, the number of skills, the characters
their names and descriptions take in the listing, and whether they are enabled for this
project, then compares the enabled total to the listing budget. Python 3.8+ standard library
only. No Python: say so, and point to `/context`, which remains the reference.

## What a profile cannot do

- **Hide a single skill of a plugin.** The granularity is the plugin. `skills` covers the
  skills outside plugins only.
- **Save many tokens by cutting skills.** Above its budget, Claude Code drops descriptions;
  cutting a plugin mostly gives descriptions back to the other skills, so Claude picks the
  right one more often. The large savings are heavy built-in tools such as `Artifact`.
  MCP tools are deferred by default (loaded on demand): denying a server keeps it out of
  reach, but saves little, and its instructions stay.
- **Allow a tool denied in the user settings.** Deny rules of every scope add up: a profile
  can deny a tool, not lift a deny set in `~/.claude/settings.json`. `--status` then shows the
  profile as partial.
- **Give two parallel sessions of the same folder two profiles at start.** They read the same
  file: open the second one after switching.

**Why not the user scope** (`~/.claude/settings.json`): it switches every session on the
machine. A project file keeps each folder on its own profile.
