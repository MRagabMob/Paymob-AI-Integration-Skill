---
description: Diagnose which stage of a Paymob sandbox payment flow is failing, without exposing secrets or customer data.
argument-hint: "[project path or failing stage, optional]"
disable-model-invocation: true
allowed-tools: Read Glob Grep Bash
---

Diagnose the Paymob sandbox flow for: $ARGUMENTS

Never ask for or print Paymob keys, HMAC values, auth/client tokens, complete callback bodies, customer PII, or `.env` contents. Use synthetic fixtures and redacted metadata only. Do not perform live-mode or money-moving actions.

## Locate the canonical files

Use the first available skill root:

1. `${CLAUDE_PLUGIN_ROOT}/skills/paymob-integration/`
2. `~/.claude/skills/paymob-integration/`
3. `skills/paymob-integration/` relative to the current repository

Read `references/sandbox-quickstart.md`, `references/webhook-troubleshooting.md`, and `references/integration-safety.md`. If you cannot read them, say so and stop; do not diagnose from memory.

## Diagnose in order

Start at configuration and stop at the first failing stage: setup → intention → checkout → callback delivery → HMAC → business binding → lifecycle/fulfillment → reconciliation.

- Run `scripts/paymob_setup_check.py` when available; it must not print values.
- Inspect code and redacted error/status metadata only.
- For HMAC logic, use `references/transaction-hmac-fixture.json` or `/paymob-check-hmac`; never request the merchant's secret.
- Treat redirect/SDK success as UX only.
- A signed callback that mismatches the stored amount, currency, Integration ID, account, mode, or attempt reference is a security failure, not a reason to override the order manually.

Return one compact table: stage, pass/fail/not-tested, evidence, and next safe action. Clearly distinguish a dashboard/account enablement issue from an application-code issue.
