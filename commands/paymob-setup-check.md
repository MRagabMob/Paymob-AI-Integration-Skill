---
description: Check Paymob local configuration safely without displaying credentials or calling live APIs.
argument-hint: "[project path, optional]"
disable-model-invocation: true
allowed-tools: Read Glob Grep Bash
---

Run a secret-safe Paymob setup preflight for the user's project: $ARGUMENTS

Never ask the user to paste keys, never print environment-variable values, never open or echo a `.env` file, and never call a live Paymob API for this command.

## Locate the checker and guide

Use the first available skill root:

1. `${CLAUDE_PLUGIN_ROOT}/skills/paymob-integration/`
2. `~/.claude/skills/paymob-integration/`
3. `skills/paymob-integration/` relative to the current repository

Read `references/credentials-and-integration-ids.md`, then locate `scripts/paymob_setup_check.py` under the same root. If you cannot read both files, say so and stop; do not reconstruct the checks from memory.

## Run

Run the script through the project's normal local secret-injection/runtime environment so it can see already-configured variables:

```bash
python <resolved-skill-root>/scripts/paymob_setup_check.py
```

The script may report only pass/fail/warn and variable names. It must never display values. Do not add shell commands such as `env`, `set`, `printenv`, `Get-ChildItem Env:`, or `cat .env`.

The checker intentionally does not open or parse `.env` files. If the project normally loads one, use its existing trusted runner; do not invent a command that echoes or exports the file in chat output.

Summarize failures first, then warnings. For dashboard-only facts—especially whether an Integration ID belongs to the selected account and Test/Live mode—direct the user to the canonical guide rather than claiming the local check proved them.
