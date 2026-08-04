# Quickstart: Configuration System

## Prerequisites

- cc-review plugin installed
- `yq` available for YAML processing

## Validation Scenario 1: Init and Config Creation

1. Run init in a project with no existing config:
   ```bash
   /cc-review:init
   ```
2. Verify it detects installed tools and test command
3. Confirm the generated config
4. Verify `.cc-review/config.yml` is written with correct values

## Validation Scenario 2: Agent Selection

1. Create `.cc-review/config.yml` with:
   ```yaml
   agents:
     test_quality: false
     goal_alignment: false
   ```
2. Run `cc-review:review`
3. Verify only 4 agents run (correctness, architecture, security, production)

## Validation Scenario 3: Profile Presets

1. Run with quick profile: `cc-review:review --profile quick`
2. Verify only correctness and security agents run
3. Run with thorough profile: `cc-review:review --profile thorough`
4. Verify all agents and external tools run

## Validation Scenario 4: Config Override

1. Create `/tmp/ci-config.yml` with custom settings
2. Run: `cc-review:review --config /tmp/ci-config.yml`
3. Verify the external config's settings are applied
4. Add a CLI flag: `cc-review:review --config /tmp/ci-config.yml --no-coderabbit`
5. Verify CLI flag overrides the config file

## Validation Scenario 5: Resolution Chain

1. Set `max_fix_rounds: 5` in `~/.cc-review/config.yml`
2. Set `max_fix_rounds: 2` in `.cc-review/config.yml`
3. Run `cc-review:review` and verify max_fix_rounds is 2 (project wins)
4. Run `cc-review:review --profile thorough` and verify max_fix_rounds is 5 (profile wins)

## Validation Scenario 6: Init Merge

1. Run init to create initial config
2. Manually edit a value in the config
3. Re-run init
4. Verify the manual edit is preserved
