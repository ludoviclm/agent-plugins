# AGENTS.md - instructions for coding agents

Read by Claude Code through `CLAUDE.md`, which only imports this file, and by other agents
(GitHub Copilot, Codex...) directly. Write here, never in `CLAUDE.md`.

## What this repository is

A Claude Code plugin that ships one skill, `context-profile`, and the marketplace that
distributes it. The skill switches per-project context profiles (enabled plugins, denied
tools) in `.claude/settings.local.json`, installs a profile's missing plugins on approval,
and measures each plugin's weight in the skill listing. A `SessionStart` hook shows the
profile of each session.

| Path | Role |
| --- | --- |
| `.claude-plugin/marketplace.json` | The marketplace: `/plugin marketplace add ludoviclm/claude-context-profile` |
| `plugins/context-profile/.claude-plugin/plugin.json` | Plugin manifest: name, version, author |
| `plugins/context-profile/skills/context-profile/SKILL.md` | The skill: the behaviour Claude follows |
| `.../profiles.example.json` | Example configuration, copied to `~/.claude/context-profiles.json` |
| `.../scripts/apply.py` | Applies profiles to `.claude/settings.local.json`; the skill's fast path; `--hook` for the banner |
| `plugins/context-profile/hooks/hooks.json` | `SessionStart` hook: the session banner, through `apply.py --hook` |
| `.../scripts/measure.py` | Listing weight per plugin |
| `README.md` | User documentation: problem, usage, install, customization, alternatives |
| `docs/context-profile.png` | Illustration shown at the top of the README |
| `tests/test_scripts.py` | End-to-end tests of both scripts, standard library `unittest` |
| `.github/workflows/ci.yml` | CI: the tests on Linux, Windows and macOS; feeds the README badge |

## Rules

- **English everywhere**: skill, README, code, comments, commit messages.
- **Nothing personal or company-specific**: no employer, client, internal repo, path or
  account. Examples use public marketplaces only. Check with
  `grep -rniE "<employer>|<internal name>" .` before a commit.
- **The skill only writes what it manages**: the plugins and tools listed in the user's
  profiles. Never add behaviour that touches an unlisted plugin, the plugin that ships the
  skill, or the user scope (`~/.claude/settings.json`).
- **Installing is always approved by the user**, at the local scope.
- **The scripts stay dependency-free** (Python 3.8+ standard library) and cross-platform (Windows, macOS, Linux). Comments
  explain the non-obvious parts only.
- **Plain hyphens**, no em dash, in all prose.

## Keeping things in sync

A change to the profile format, the requests the skill understands, or its limits goes in
`apply.py`, `SKILL.md` (including its no-Python fallback) **and** `README.md` (sections "How it works", "Customizing the skill", "Limits").
A change to the example profiles goes in `profiles.example.json` and the README tables.

Figures quoted in the README (skill counts, characters, budget) carry their date and version:
re-measure with `measure.py` rather than editing them by hand.

## Before a commit

1. `claude plugin validate .` passes, without warnings.
2. `python -m unittest discover -s tests` passes (it also checks that the JSON files parse).
   A behaviour change comes with its test.
3. Behaviour change: bump `version` in `plugin.json` (semantic versioning).

Test a change for real in a throwaway folder: add this repository as a local marketplace
(`claude plugin marketplace add <path>`), install the plugin with `--scope local`, switch a
profile, then check the result in a new session with `/context`.
