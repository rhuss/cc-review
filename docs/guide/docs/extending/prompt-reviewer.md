# Write a prompt reviewer

<!-- Sources:
cc-review:README.md:309-323
cc-review:docs/reviewer-plugins.md:3
cc-review:docs/reviewer-plugins.md:5-15
cc-review:docs/reviewer-plugins.md:31
cc-review:docs/reviewer-plugins.md:41-66
cc-review:docs/reviewer-plugins.md:68-82
cc-review:docs/reviewer-plugins.md:84-114
cc-review:review/core/schemas/reviewer.schema.json:6-28
-->

A reviewer is a plugin, and a prompt reviewer is the simplest kind: one Markdown file with a short YAML frontmatter block and a prompt body. You add one by dropping that file into a directory the review scans, and no core file, configuration template, or command definition changes. The body is the instruction set a fresh-context review agent follows when it reads your changed files and reports findings.

Discovery runs on every review and scans three layers: your project's `.cc-review/reviewers/`, your personal `~/.cc-review/reviewers/`, and the reviewers bundled with the plugin. A project reviewer lives with the code it reviews. A reviewer in `~/.cc-review/reviewers/` follows you across every project. When the same name appears in more than one layer, the higher layer wins, so a project or user reviewer can replace a bundled one by reusing its name.

The steps below build an accessibility reviewer for UI code.

1. **Create the file.** For a reviewer that belongs to one project, create the reviewer directory in the repository root and add a file named for the reviewer:

   ```bash
   mkdir -p .cc-review/reviewers
   ```

   Then create `.cc-review/reviewers/accessibility.md`. For a reviewer you want in every project, create it under `~/.cc-review/reviewers/` instead.

2. **Write the frontmatter.** A prompt reviewer needs two fields and takes two more that are worth setting:

   - `name` (required): the reviewer's identifier. It must be lowercase letters, digits, and hyphens, and it must equal the file basename, so `accessibility.md` carries `name: accessibility`. A short list of names is reserved because they collide with command flags, among them `only`, `fix`, `pr`, and `spec`.
   - `kind` (required): `prompt` for a reviewer whose body is the prompt the agent runs.
   - `display_name` (optional, defaults to `name`): the label shown in the console summary and the findings report.
   - `category` (optional, defaults to `name`): written to the `category` field of every finding this reviewer reports. It too is lowercase letters, digits, and hyphens.

   Unknown fields are ignored rather than rejected, so the format can grow without breaking older reviewers. The full contract is `review/core/schemas/reviewer.schema.json`.

3. **Write the prompt body.** The body is the reviewer prompt. Write it for an agent that reads the changed files itself and reports findings, and do not mention harness tools. Give it three parts: a role (what this reviewer is responsible for), a scope (what it is not responsible for, so it stays in its lane), and a checklist of concrete things to look for. Report severities directly as Critical, Important, Minor, or Notable.

   > [!NOTE]
   > At dispatch the core prepends a shared preamble (anti-sycophancy, distrust, confidence scoring, and the output format), and it is always applied with no opt-out. Do not repeat those rules in your body, and remove anything that conflicts with them, such as instructions to praise good code. Your body follows the preamble, and after it come the review target, the spec and review hints when present, and the output contract.

   The complete `.cc-review/reviewers/accessibility.md` looks like this:

   ```markdown
   ---
   name: accessibility
   display_name: "Accessibility"
   kind: prompt
   category: accessibility
   ---
   You are the ACCESSIBILITY REVIEW AGENT.

   YOUR ROLE: You ARE responsible for finding accessibility defects in UI code:
   missing alternative text, unlabeled form controls, keyboard traps, color-only
   signaling, and ARIA misuse.

   YOU ARE NOT RESPONSIBLE FOR: correctness bugs, security, performance, or
   test quality. Stay in your lane.

   For each changed file that renders UI, check:
   - Every image and icon has meaningful alternative text or is marked decorative
   - Every form control has an associated label
   - Interactive elements are reachable and operable with the keyboard
   - Information is not conveyed by color alone
   - ARIA roles and attributes match the element's behavior

   Report each defect as a finding with the exact element and line.
   ```

4. **Commit the file and run a review.** Discovery picks the reviewer up on the next run, dispatches it alongside the built-ins with the shared preamble prepended, and shows its row in the console summary (here "Accessibility"). Its findings carry `source_agent: accessibility` and `category: accessibility`. Run only your reviewer with `/review --only accessibility`, or turn it off for one run with `/review --no-accessibility`.

Check: the file sits in the project reviewer directory that discovery scans, so the next review runs it.

```bash
ls .cc-review/reviewers/accessibility.md
```
<!-- expect: contains "accessibility" -->

Project prompt reviewers run without any trust step. A reviewer that wraps an external command-line tool uses `kind: command` instead of `kind: prompt`.

> [!NOTE]
> This page was verified against cc-review <!-- guide:attr cc-review-version -->1.4.0<!-- /guide:attr -->.
