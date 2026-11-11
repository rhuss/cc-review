# CI Contract

Comment grammar: a whole trimmed comment `/cc-review (review|triage|assess|fix|help)`; arbitrary appended commands are rejected. PR-only operations are review/triage/fix; assess is issue-only.

Run requests: `python3 review/core/scripts/ci.py select --event EVENT --event-file PATH --config PATH`; output is matrix JSON. `prepare --request JSON --config PATH --work-dir PATH` writes snapshot/prompt and runner outputs. `finish --work-dir PATH --result PATH` validates structured output and records terminal status. All mutable API calls use gh with input JSON through stdin and explicit methods.

Publication limits: COMMENT only, no closures, bot-thread replies/resolution only, configured assessment labels only, explicit writer same-repo fixes only. Unattended interaction defaults are shared in `commands/unattended.md`. Model output is untrusted until deterministic validation succeeds.

Provider secrets never enter item snapshot, generated config or prompt. Invalid configuration and selection errors fail the workflow; accepted item failures become needs_attention and fail the worker after status/summary publication.
