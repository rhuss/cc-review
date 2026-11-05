# Invoking cc-review across harnesses

<!-- Sources:
cc-review:review/.claude-plugin/plugin.json:2
cc-review:review/skills/review/SKILL.md:2
cc-review:review/.codex-plugin/plugin.json:1-11
cc-review:review/opencode/install.sh:19-25
url:https://code.claude.com/docs/en/skills
url:https://learn.chatgpt.com/docs/build-skills
url:https://opencode.ai/docs/commands/
-->

cc-review ships its commands as skills, one skill per command (`review`, `triage`, `inbox`, `issue`, and `init`), and each harness has its own way to call them. The call syntax is the only thing that changes between harnesses; the command itself does the same work wherever you start it.

**Convention:** the examples throughout this guide use Claude Code syntax, for example `/cc-review:review`. On another harness, translate the call using the table below.

## Calling a command on each harness

| Harness | How you call a command | Example (review) |
|---------|------------------------|------------------|
| Claude Code | The plugin-prefixed slash command `/cc-review:<command>` always works. The bare `/<command>` works only when no other installed command shares that name. | `/cc-review:review` |
| Codex | Type `$` followed by the bare skill name, with no plugin namespace: `$review`, `$triage`, `$inbox`, `$issue`, `$init`. You can also run `/skills` to pick from a list, or just describe the task and let Codex match the skill. There is no `$cc-review:review` namespace form. | `$review` |
| OpenCode | The bare slash command, with no namespace: `/review`, `/triage`, `/inbox`, `/issue`. | `/review` |

> [!IMPORTANT]
> The OpenCode commands do not register out of the box at this version. As of OpenCode v2.1.4, OpenCode discovers commands only from `.opencode/command/` in the project or `~/.config/opencode/commands/` globally. The cc-review OpenCode installer copies the command files to `.opencode/plugins/cc-review/command/`, a path stock OpenCode does not scan, so `/review` and the other commands will not appear until those files are placed in `.opencode/command/`. Check the cc-review project for a fix, or move the files into `.opencode/command/` yourself.

## How the Claude prefix is decided

On Claude Code, a skill is addressable both by its bare name and by its plugin-qualified name. The bare `/review` resolves as long as no other installed skill or command claims the name `review`. When two commands share a name, the bare form is ambiguous, and the plugin prefix picks the one you mean: `/cc-review:review`. Because the prefixed form always resolves, it is the safe choice to write down and share.

## Translating examples

The rest of this guide writes commands in Claude Code form, `/cc-review:<command>`. To follow along on another harness, swap the call: use `$<command>` on Codex (for example `$review`) and `/<command>` on OpenCode (for example `/review`). The flags and the behavior are the same in every case.
