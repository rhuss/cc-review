# cc-review Guide style guide

Project terms and rules that every page follows, on top of the built-in style rules (or the cc-prose voice profiles when cc-prose is installed). Page implementers and reviewers read this file. Keep one rule per bullet.

## Terms

- "cc-review" is the subject of this guide: a multi-agent code review plugin for AI coding agents. Always lowercase, even at the start of a sentence.
- Product and tool names are spelled exactly: cc-review, Claude Code, Codex, OpenCode, CodeRabbit, GitHub Copilot, Greptile.
- Harness means one of the three AI coding agents cc-review plugs into: Claude Code, Codex, OpenCode. It is a domain term; prose-check hits for this sense are false positives.
- Reviewer means one review agent or external tool in the panel (for example Correctness, Security, Codex). A lane is the same idea seen as a column of the panel.
- Finding means one structured issue a reviewer reports (severity, confidence, file, line, fix). A domain term.
- Skeptic and Calibrator are the two meta-review critics; capitalize them as names.
- Gate means the pass or fix decision (Critical plus Important equals zero passes). Fix loop means the apply, test, re-review cycle.
- Gator is the opt-in principal-engineer reviewer persona; spell it with a capital G.
- Persona names: "Developer" (the reader who runs cc-review) and "Plugin author" (the reader who extends it).

## Rules

- No em dash or en dash characters.
- This is a GitHub Markdown (gfm) guide. The one-sentence-per-line rule does not apply here; write natural paragraphs.
- Versions and commits come from the baseline attributes, never typed.
- Measured results (precision scores, fix rates, OpenShell numbers) are reported measurements; attribute each to its data input and link the public pull request when one is named. Do not present a measured number as a code-verifiable fact.
- Task pages: a short paragraph on why, then numbered steps, then a `Check:` line with the expected result.
- Every factual sentence about cc-review behavior must trace to a pinned source location.
