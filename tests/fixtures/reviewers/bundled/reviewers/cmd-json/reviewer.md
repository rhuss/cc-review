---
name: cmd-json
display_name: "Fake JSON Tool"
kind: command
category: external
detect: "true"
invoke: "tests/fixtures/reviewers/bundled/reviewers/cmd-json/emit.sh --base {base_branch} {files}"
timeout_seconds: 5
severity_map:
  major: Important
output:
  format: json
---
Parsing notes: the tool prints a JSON array of findings.
