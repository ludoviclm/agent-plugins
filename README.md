# agent-plugins

[![CI](https://img.shields.io/github/actions/workflow/status/ludoviclm/agent-plugins/ci.yml?branch=main&logo=github&label=CI)](https://github.com/ludoviclm/agent-plugins/actions/workflows/ci.yml)
[![license](https://img.shields.io/github/license/ludoviclm/agent-plugins)](LICENSE)

The `ludoviclm` plugin marketplace: plugins for coding agents, starting with Claude Code.

## Plugins

| Plugin | What it does | Harnesses |
| --- | --- | --- |
| [`context-profile`](plugins/context-profile/README.md) | Switches context profiles per project: load only the plugins, skills and tools the work needs, and measure each plugin's weight in the skill listing. | Claude Code |

"Harnesses" lists where a plugin works, not only where it installs: GitHub Copilot CLI and
VS Code read this marketplace too, but a plugin that manages Claude Code settings does
nothing useful there.

## Install

In Claude Code:

```text
/plugin marketplace add ludoviclm/agent-plugins
/plugin install <plugin>@ludoviclm
```

## Layout

```text
.claude-plugin/marketplace.json   the marketplace: name "ludoviclm", one entry per plugin
plugins/<plugin>/                 one folder per plugin, with its manifest and README
tests/test_<plugin>.py            tests, run by the CI on Linux, Windows and macOS
```

## License

[MIT](LICENSE)
