# AGENTS.md - instructions for coding agents

Read by Claude Code through `CLAUDE.md`, which only imports this file, and by other agents
(GitHub Copilot, Codex...) directly. Write here, never in `CLAUDE.md`.

## What this repository is

The `ludoviclm` plugin marketplace (`/plugin marketplace add ludoviclm/agent-plugins`) and
the plugins it distributes, one folder each under `plugins/`.

| Path | Role |
| --- | --- |
| `.claude-plugin/marketplace.json` | The marketplace: name `ludoviclm`, one entry per plugin |
| `README.md` | The marketplace page: plugin table with the harnesses each one supports, install |
| `plugins/<plugin>/` | One plugin: `.claude-plugin/plugin.json`, its skills, hooks and `README.md` |
| `tests/test_<plugin>.py` | Tests of one plugin, standard library `unittest` |
| `.github/workflows/ci.yml` | CI: all the tests on Linux, Windows and macOS; feeds the README badges |
| `docs/` | Images shown in the READMEs |
| `docs/src/` | HTML source of each image: change the source, then re-render the PNG (below) |

## Rules

- **English everywhere**: skills, READMEs, code, comments, commit messages.
- **Nothing personal or company-specific**: no employer, client, internal repo, path or
  account. Examples use public marketplaces only. Check with
  `grep -rniE "<employer>|<internal name>" .` before a commit.
- **Each plugin states its harnesses** in the table of the root `README.md`: where it
  works, not only where it installs.
- **Scripts stay dependency-free** (Python 3.8+ standard library) and cross-platform
  (Windows, macOS, Linux). Comments explain the non-obvious parts only.
- **Plain hyphens**, no em dash, in all prose.

## Adding a plugin

1. `plugins/<plugin>/` with `.claude-plugin/plugin.json` (`homepage` pointing to its folder)
   and a `README.md`.
2. An entry in `.claude-plugin/marketplace.json` and a row in the root `README.md`.
3. Its tests in `tests/test_<plugin>.py`.

## Images

Each PNG in `docs/` is a screenshot of its HTML source in `docs/src/`, taken with a headless
Chromium browser (Chrome or Edge):

```bash
chrome --headless=new --hide-scrollbars --force-device-scale-factor=<1|2> \
  --window-size=<width>,<height> --screenshot=docs/<name>.png docs/src/<name>.html
```

`context-profile.png`: 1200x1500, scale 1. `context-profile-session.png`: 1200 wide, scale 2,
then trim the empty bottom of the page. Keep the colour tokens of `context-profile.html` in
every image.

## Plugin `context-profile`

A skill that switches per-project context profiles (enabled plugins, denied tools) in
`.claude/settings.local.json`, installs a profile's missing plugins on approval, and
measures each plugin's weight in the skill listing. A `SessionStart` hook shows the profile
of each session. Claude Code only.

| Path (under `plugins/context-profile/`) | Role |
| --- | --- |
| `skills/context-profile/SKILL.md` | The skill: the behaviour Claude follows |
| `.../profiles.example.json` | Example configuration, copied to `~/.claude/context-profiles.json` |
| `.../scripts/apply.py` | Applies profiles to `.claude/settings.local.json`; the skill's fast path; `--hook` for the banner |
| `.../scripts/measure.py` | Listing weight per plugin |
| `hooks/hooks.json` | `SessionStart` hook: the session banner, through `apply.py --hook` |
| `README.md` | User documentation: problem, usage, install, customization, alternatives |

Its rules:

- **The skill only writes what it manages**: the plugins and tools listed in the user's
  profiles. Never add behaviour that touches an unlisted plugin, the plugin that ships the
  skill, or the user scope (`~/.claude/settings.json`). The skill recognises itself by
  plugin name (`context-profile@`), whatever the marketplace is called.
- **Installing is always approved by the user**, at the local scope.
- **Keeping things in sync**: a change to the profile format, the requests the skill
  understands, or its limits goes in `apply.py`, `SKILL.md` (including its no-Python
  fallback) **and** the plugin's `README.md` (sections "How it works", "Customizing the
  skill", "Limits"). A change to the example profiles goes in `profiles.example.json` and
  the README tables.
- Figures quoted in its README (skill counts, characters, budget) carry their date and
  version: re-measure with `measure.py` rather than editing them by hand.

## Before a commit

1. `claude plugin validate .` passes, without warnings; so does
   `claude plugin validate plugins/<plugin>` for each plugin changed.
2. `python -m unittest discover -s tests` passes (it also checks that the JSON files parse).
   A behaviour change comes with its test.
3. A plugin changed: bump `version` in its `plugin.json` (semantic versioning).

Test a change for real in a throwaway folder: add this repository as a local marketplace
(`claude plugin marketplace add <path>`), install the plugin with `--scope local`
(`<plugin>@ludoviclm`), then check the result in a new session.
