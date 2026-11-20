# How it works

<!-- Sources:
cc-review:README.md:3
cc-review:README.md:11
cc-review:README.md:14
cc-review:README.md:347-408
cc-review:review/core/commands/review.md:815-931
cc-review:review/core/commands/review.md:992,1020-1023,1092-1103
-->

cc-review is a multi-agent code review plugin for the AI coding agents Claude Code, Codex, and OpenCode. Each prompt reviewer reads your changes in its own fresh context. When the run has enough findings, two critics filter the merged findings, and a fix loop resolves the blocking ones and re-reviews, up to the round limit. What reaches you at the end is one report of fewer, higher-confidence issues, with the blocking findings resolved where the loop could fix them, rather than the raw output of every reviewer and tool. The pages below take that run apart one layer at a time.

The pages, in reading order:

- [The review pipeline](pipeline.md) walks the stages a single run moves through, from discovering the reviewers to writing the final report.
- [Reviewers](reviewers.md) describes the panel itself: the six built-in lanes, the external tools, the opt-in Gator reviewer, a principal-engineer persona, and the rules every reviewer follows.
- [Meta-review](meta-review.md) covers the two critics, the Skeptic and the Calibrator, that judge the merged findings before anything is acted on.
- [Gate and fix](gate-and-fix.md) explains the pass-or-fix gate and the autonomous loop that clears the blocking findings so the gate can pass.
- [Measured results](results.md) reports how cc-review has performed in practice, as dated measurements from recorded runs on public and local code.
