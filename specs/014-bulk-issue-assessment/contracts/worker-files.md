# Contract: Worker Files

## Assessment worker → `items/<n>/assessment.json`

Written with the file-write tool, never through a shell literal.

```json
{
  "body": "reply to the reporter",
  "assessment": { "...": "fields of templates/issue-assessment.md, validated by assessment.validate" },
  "fix_estimate": {
    "confirmed": true,
    "files": 1,
    "lines": 20,
    "test_lines": 30,
    "note": "where the change goes, one sentence"
  }
}
```

- `fix_estimate` is required for every recommendation (spec FR-013). `files`, `lines`, `test_lines` are non-negative integers. `confirmed` means the problem was confirmed in the code (bugs, and then `assessment.check.result` must be `confirmed`) or the change is clearly bounded (other kinds).
- When the snapshot lists open non-maintainer linked pull requests, the assessment text names each with its URL (FR-014).
- The worker reads only `items/<n>/snapshot.json`, the bundled templates, and project files inside the verified root. It runs no commands, asks the maintainer nothing, and never issues a definitive decline when the snapshot reports incomplete history.

`render-item` computes `fix_eligible = recommendation == "pursue" and confirmed and files <= 3 and lines <= 100 and test_lines <= 300 and run.fixes_available and no open non-maintainer linked PR`.

## Fix worker → `items/<n>/fix.json`

```json
{ "status": "done", "summary": "what changed and why, 1 to 3 sentences", "reason": "" }
```

- `status` is `done` or `gave_up` (with `reason`).
- The worker edits files only inside `worktrees/<n>/`, runs no commands (no tests, builds or scripts), makes no network calls, and never commits, pushes or opens anything (FR-022a, FR-024). Where the harness supports it, it has only file read, edit and write tools.
- Issue text stays untrusted: the worker implements only the change described by the approved assessment.
- The summary is sanitized by `fix-publish` before it reaches the PR body.
