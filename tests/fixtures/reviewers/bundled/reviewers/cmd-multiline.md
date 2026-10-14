---
name: cmd-multiline
kind: command
detect: |
  false ||
  true
invoke: |
  echo review
  echo pr {pr_number}
output:
  format: json
---
