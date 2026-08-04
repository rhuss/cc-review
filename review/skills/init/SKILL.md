---
name: init
description: Initialize cc-review configuration by detecting tools and generating config
argument-hint: "[--interactive]"
---

# Init

Locate cc-review core and delegate to `core/commands/init.md`.

## Core Resolution

Find the cc-review core directory by checking these paths in order:
1. `./core` relative to this plugin's root directory
2. `.cc-review/core` in the current project
3. `~/.cc-review/core` in the user's home directory

Read the first path that contains `commands/init.md`. If none found, report:
"cc-review core not found. Install the plugin or set up .cc-review/core."

## Execution

Read and execute `core/commands/init.md` from the resolved core path.

Pass through all arguments from the user's invocation:
- `--interactive`: Walk through each config section with questions
