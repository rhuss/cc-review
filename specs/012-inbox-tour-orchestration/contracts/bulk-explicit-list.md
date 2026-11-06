# Contract: Bulk Explicit Pull-Request List

New selector that lets `bulk` run on an exact list of pull requests, so `inbox` can hand off a tour selection (FR-017, FR-018).

## `bulk-select.sh` explicit mode

New invocation:

```
bulk-select.sh review  --prs <n,n,...> [--limit <n>] --user <login>
bulk-select.sh triage  --prs <n,n,...> --user <login>
```

- Resolves exactly the given PR numbers through the existing shared assessor (`pr_actions.py select`), the same assessor used by the `default`/`all-open`/`search` modes.
- Prints the unchanged contract on stdout: `{"selected": [PrEntry seed], "excluded": [Exclusion]}`.
- A requested PR that bulk would not act on appears in `excluded` with its reason (never silently dropped) (FR-018).
- Validation (exit 2 on usage error): `--prs` values must be positive integers; `--prs` is mutually exclusive with `--all-open`, `--search`; numbers are de-duplicated preserving order.
- Exit codes unchanged: 0 ok, 1 failure, 2 usage error, 75 rate limit.

## Threading through the commands

- `review.md` / `triage.md` bulk handoff: accept `--prs <list>` together with `--bulk`; reject `--prs` with `--pr` (`Error: --prs and --pr cannot be combined`) and with `--all-open`/`--search`, mirroring existing selector validation.
- `bulk.md`: accept the list, record selector kind `explicit` (value: the PR list) in run state alongside the existing selector record, and pass `--prs` to `bulk-select.sh`. The rest of the bulk pipeline (worktrees, analysis loop, decision table, apply, resume) is unchanged.

## Authority

`inbox` passes the list unfiltered and holds no separate selection logic. `bulk` is the single eligibility authority (SC-004); divergences surface as `excluded` entries the decision table shows.
