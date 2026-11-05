# Reviewers

<!-- Sources:
cc-review:review/core/reviewers/correctness.md:9-15
cc-review:review/core/reviewers/architecture.md:9-17
cc-review:review/core/reviewers/security.md:9-17
cc-review:review/core/reviewers/production.md:9-17
cc-review:review/core/reviewers/test-quality.md:9-17
cc-review:review/core/reviewers/goal-alignment.md:1-21
cc-review:review/core/agents/preamble.md:22-55
cc-review:review/core/reviewers/gator/reviewer.md:1-32
cc-review:review/core/reviewers/gator/reviewer.md:159-166
cc-review:review/core/reviewers/gator/references/findings-contract.md:1-57
cc-review:review/core/reviewers/codex.md:1-6
cc-review:review/core/reviewers/copilot.md:1-6
cc-review:review/core/reviewers/coderabbit/reviewer.md:1-6
cc-review:review/core/reviewers/greptile/reviewer.md:1-6
cc-review:README.md:366-380
-->

A reviewer is one voice in the panel. cc-review ships three kinds: six built-in prompt reviewers, each a review agent with a single job; a set of external command-line tools it can call and fold into the same report; and one opt-in principal-engineer persona. The [pipeline](pipeline.md) page covers how a run discovers and dispatches them. This page is about what each one is for and the rules they all follow.

## The six lanes

The bundled prompt reviewers divide the work into six lanes. Each lane owns one kind of problem, and nothing else.

- **Correctness** finds bugs: mutation safety, shared references, logic errors, resource cleanup, error-path correctness, off-by-one errors, null handling, and type confusion.
- **Architecture** judges structure and idioms: dead code, unnecessary complexity, duplication, misleading naming, comment accuracy, abstraction level, and convention adherence.
- **Security** looks for vulnerabilities: input validation, injection, secrets handling, authentication and authorization, path traversal, deserialization safety, and rate limiting.
- **Production Readiness** catches what fails in operation: resource leaks, unbounded growth, concurrency issues, error amplification, graceful shutdown, and observability gaps.
- **Test Quality** weighs the tests themselves: coverage gaps, weak assertions, tests that pass for the wrong reason, empty stubs, and missing edge cases.
- **Goal Alignment** checks that the change fits the project: the need and fit of the pull request description and its linked issues, whether the code delivers its stated goals, and whether it smuggles in undeclared changes. This lane needs a pull request to review, so it runs only when one is supplied.

### Stay in your lane

Each lane reviewer is told what it is responsible for, and then told what it is not. The Correctness reviewer is not responsible for style, test coverage, security, or architecture; the Security reviewer is not responsible for general correctness or production readiness; and so on around the panel. Every one of the six ends the same way: those concerns belong to other agents, so stay in your lane.

The role gate is what keeps the panel from collapsing into one blurry opinion repeated six times. Because each reviewer runs in its own fresh context and sees only its own slice of the problem, two reviewers rarely file the same issue, and the merge step has clean, single-category findings to work with rather than overlapping restatements.

## The shared preamble

Every prompt reviewer, the six lanes and the opt-in persona alike, is prepended with a common preamble. It sets the rules of evidence that make a finding trustworthy.

- **Judge what was built, not what was intended.** A reviewer distrusts the implementer's report, comments, and commit messages, and verifies everything by reading the actual code. Comments may be wrong, names may mislead, and a test name may not match what the test checks.
- **Review the code and the spec, nothing else.** A reviewer does not read the git log, commit messages, brainstorm documents, or the plan and task files. Those reveal what the author meant to do and bias the review toward confirming it. The code and the spec are the only trustworthy record of what was built.
- **No praise.** A reviewer starts directly with its findings, not with an affirmation of the work.
- **Score every finding by confidence.** A reviewer rates each finding from 0 to 100 and reports only those at a confidence of 70 or higher. The one exception is a Critical finding, which may be reported at 50 or higher, so a serious but uncertain risk is still surfaced.
- **Zero findings is a valid result.** After a thorough review, finding nothing is an acceptable outcome. A reviewer does not inflate nits, invent issues, or expand its scope to avoid an empty report.

## The external reviewers

Alongside the built-in lanes, cc-review can call external command-line review tools and parse their output into the same finding shape, so a tool's results sit beside the agents' findings in one report. Four are bundled, and they differ in whether a fresh install runs them.

- **CodeRabbit** runs by default.
- **Codex CLI** runs by default.
- **Copilot** is off by default.
- **Greptile** is off by default. It also needs the repository connected to a Greptile organization, and it spends credits on every run, which is another reason it stays off until you turn it on.

An external reviewer runs only when its command-line tool is both installed and enabled, so the two that are on by default still contribute nothing on a machine where their tools are absent.

## The gator persona

Gator is an opt-in reviewer that takes the stance of a principal engineer rather than a single-lane specialist. Its reviewer id is `gator`, and it ships disabled, so a default run never includes it. It was ported from the NVIDIA OpenShell project.

Where the six lanes each hold one concern, Gator balances three at once.

- **Pragmatism**: is the solution as simple as the problem allows, or is it over-engineered?
- **User empathy**: how the change lands on the people who use, operate, and maintain the system.
- **Security**: threat surfaces, trust boundaries, and input validation, weighed against established frameworks.

What sets Gator apart is its evidence contract. A blocking finding, one it rates Critical or Warning, is only allowed to block when its failure scenario carries a full chain of evidence. That chain names the invariant the change violates, the prerequisite capability to reach it, the entry point and the sink, the behavior before and after the change, the observable impact, why this change owns the problem, a concrete requested fix, and a minimal deterministic reproducer. A candidate that cannot meet every item is not dropped; it is reported as a non-blocking Suggestion that names the evidence it is missing. The contract is what lets a single broad reviewer stay as disciplined as the focused lanes: an opinion only earns the power to block when it can prove itself.

Once a run collects every reviewer's findings, two meta-review critics judge them before anything is acted on. The [meta-review](meta-review.md) page covers that stage.
