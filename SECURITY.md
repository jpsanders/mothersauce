# Security

## Reporting a vulnerability

Please report security problems privately, through GitHub's
[private vulnerability reporting](https://github.com/jpsanders/mothersauce/security/advisories/new), not in a public
issue. You will get an answer within a week.

## What mothersauce does on your machine

The command, the MCP server and the skill read files shipped inside the package and print them. Nothing touches the
network. Three commands write, and only when you run them:

- `mothersauce man --install` writes one file to your per user man folder.
- `mothersauce integrate` runs `claude mcp add` and `codex mcp add` where those commands exist, edits the
  configuration files of Codex (without its command), OpenCode, Gemini CLI and Cursor after a backup named
  `*.mothersauce.bak`, and writes the skill into the skills folders of Claude Code, Codex and OpenCode. It never edits
  Claude Code's own configuration file. `--dry-run` shows the changes first.
- `mothersauce run <recipe>` runs that recipe's demo, which writes only to temporary folders and in memory databases
  it removes afterwards.

The MCP server's tools are all read only, and they say so to the harness.

## What the recipes teach

Several recipes exist to prevent security bugs: `sql` makes injection impossible by construction, `logging` masks the
usual shapes of a secret in messages, extra fields and tracebacks, `config` keeps passwords out of `repr` and dumps,
and `dataclasses` hides a credential from tracebacks. If one of them falls short of what it promises, that is a
vulnerability: please report it the same way.
