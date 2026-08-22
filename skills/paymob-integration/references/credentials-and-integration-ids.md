# Credentials and Integration IDs

Use this guide when a merchant is onboarding, cannot find a key, receives an Integration ID error, or is preparing test/live configuration. Keep all secret values out of chat, screenshots, logs, source control, and issue trackers.

Official guide: https://developers.paymob.com/paymob-docs/need-help/setup-guides/getting-integration-credentials

## Credential path

1. Sign in to the **Accept Dashboard**.
2. Open **Settings**.
3. Under **Developers**, open **API Keys**.
4. Copy each value directly into the server's secret manager or local `.env`; do not paste it into the AI conversation.

| Value | Purpose | Where allowed |
|---|---|---|
| Secret Key | Intention and authenticated payment APIs | Server only |
| Public Key | Launch Unified Checkout / supported client SDKs | Frontend allowed |
| HMAC Secret | Verify callbacks | Server only |
| API Key | Generate short-lived auth tokens for documented inquiry/legacy-auth exceptions | Server only |

Use test values first. Test and live keys are different except where the current dashboard/docs explicitly say otherwise.

## Integration ID path

1. In **Settings**, open **Payment Integrations**.
2. Select the required payment method, such as Cards, Mobile Wallets, Apple Pay, or another enabled method.
3. Confirm the dashboard mode is **Test** or **Live**.
4. Copy the numeric Integration ID for that exact method and mode.
5. Store one environment variable per method, for example `PAYMOB_INTEGRATION_ID_CARD` and `PAYMOB_INTEGRATION_ID_WALLET`.

An Integration ID is not a key and should never replace the Secret Key or Public Key. It still belongs in server configuration because it selects the merchant account's enabled payment method.

## Mode and region checklist

Before creating an Intention, confirm all of the following:

- `PAYMOB_MODE` is explicitly `test` or `live`.
- Secret Key and Public Key belong to the same mode.
- Every Integration ID belongs to that same mode and Paymob account.
- `PAYMOB_REGION` selects Egypt, UAE, KSA, or Oman.
- The regional base URL exactly matches `intention-api.md`.
- Currency and three-letter billing country match the merchant's market and transaction.

A `404 Integration ID does not exist` usually means a test/live mismatch, wrong regional host, wrong account, or a method that is not enabled.

## Minimum local configuration

Configure every item below before running the setup check:

| Variable | Requirement |
|---|---|
| `PAYMOB_REGION` | `egypt`, `uae`, `ksa`, or `oman` |
| `PAYMOB_MODE` | `test` for the event/sandbox flow |
| `PAYMOB_BASE_URL` | Exact regional HTTPS origin from `intention-api.md`; it must match `PAYMOB_REGION` |
| `PAYMOB_SECRET_KEY` | Test Secret Key, server only |
| `PAYMOB_PUBLIC_KEY` | Test Public Key |
| `PAYMOB_HMAC_SECRET` | Test HMAC Secret, server only |
| `PAYMOB_INTEGRATION_ID_*` | At least one numeric Test Integration ID |
| `APP_URL` | Public HTTPS application origin used to build callback/return URLs; no path or query |

The API Key is optional for initial checkout and required only when adding Transaction Inquiry/reconciliation.

## Safe handling

- Ask the merchant to confirm that a value is configured, not to reveal the value.
- Never request keys in a prompt, command argument, screenshot, ticket, or pasted `.env` file.
- Never print environment-variable values in a setup diagnostic.
- If a secret was shared accidentally, stop using it and rotate it in the dashboard before continuing.
- Use separate secret-manager entries for test and live deployments.

The bundled `scripts/paymob_setup_check.py` reads only its inherited process environment and intentionally never opens `.env` files. Run it through the project's normal trusted secret-injection/runtime path. It performs local presence and consistency checks without displaying credential values, but it cannot prove that an Integration ID is enabled or belongs to the selected mode; confirm that in the dashboard or with an authorized account-side check.
