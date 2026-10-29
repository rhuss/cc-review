# Assess Contract

## Invocation
`assess <positive-issue-number-or-https://github.com/owner/repo/issues/N> [--repo owner/repo]`

An issue URL determines repository identity unless --repo agrees case-insensitively. Plain numbers use --repo or current gh repository context. Accept only GitHub.com canonical issue URLs, with no query, fragment, credentials, ports, or extra path. Reject PR URLs, nonpositive integers, invalid repository segments, conflicting targets, and unsupported flags before gh execution. --help performs no I/O.

## Collection
Resolve repository with gh repo view (JSON nameWithOwner,url), validate identity, capture a matching local origin/root, then issue a static read-only GraphQL query using typed number input. Reject a PullRequest union result. A missing Issue or invalid required identity is an error, not an empty success. Return only canonical source metadata and sanitized bounded content. Partial usable issue data produces explicit coverage warnings.

Snapshot fields are in [data-model.md](../data-model.md). Service access is only repo view and api graphql query, with at most 30 seconds per call. Local git preflight is read-only and bounded. No shell evaluation or mutation command exists.

## Agent behavior
Read the shared workflow. Use matching target-project evidence, distinguish problem from solution and project fit, and make a genuine recommendation. Ask the maintainer before finalizing materially uncertain direction; ask the author for absent use cases in the draft. Do not turn missing evidence into rejection.

## Output
Maintainer assessment: recommendation, need, fit, evidence, uncertainty, collection/project limitations.
Public reply draft: concise welcoming prose, using prose humanizer when available or bundled maintainer voice otherwise. Display fallback information privately.
No publishing or issue/repository mutation. Temporary files are outside the invoking checkout and removed on success, error, or canceled questioning.
