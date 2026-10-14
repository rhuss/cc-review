# Evidence contract for gator findings

Every Critical or Warning finding you report must be backed by evidence.
Each evidence item below must be present, in the finding's
`failure_scenario`, before you may report a finding at Critical or
Warning. A Critical or Warning that is missing any evidence item is not a
blocker; report it as a Suggestion instead and say which evidence is missing.
Do not invent evidence to fill a gap.

## Evidence items

Put the following in the finding's `failure_scenario` field (the review
core stores it as the finding's `rationale`), each as a short labeled
sentence in this order:

- **Invariant**: the complete contract shared by all equivalent cases that the
  change violates.
- **Prerequisite**: the attacker or operator capability required to reach the
  case.
- **Entry point**: the supported API, CLI, protocol, or runtime path through
  which the case is reached.
- **Sink**: the operation where the defect becomes observable.
- **Base behavior**: what the code did before this change.
- **Head behavior**: what the code does after this change, and how that
  introduces or materially worsens the problem.
- **Observable impact**: the concrete security, data-loss, correctness, or
  maintainability consequence.
- **PR ownership**: why this change owns or worsens the problem (as opposed to
  a pre-existing defect that the change merely sits next to).
- **Requested change**: a proportionate fix that closes the invariant, shown
  concretely rather than described.

Put the following in the finding's `failure_scenario`:

- **Reproducer**: a minimal deterministic test or constrained reproduction
  (inputs, state, steps, expected versus actual outcome).

The finding's `file` and `line` point at the changed location that introduces
or worsens the exposure.

## Severity

Use your native severities and let the orchestrator translate them:

- `Critical`: must fix before merge; correctness bugs, security flaws, data
  loss risks, with the full evidence set.
- `Warning`: must fix before merge when the change introduces or materially
  worsens a concrete, reachable correctness, security, or maintainability
  problem, with the full evidence set.
- `Suggestion`: non-blocking improvement, or a Critical/Warning candidate
  whose evidence is incomplete.

## Grouping

When one invariant is violated at several sites, report one finding at the
first site and list the other sites in the `failure_scenario` under **Sibling sites**.
Do not report a second finding for the same invariant.

## Presentation

These evidence labels structure your reasoning; keep them terse. The
finding's `summary` and `short_summary` stay human-first: what is wrong and
where, in one sentence.
