# Sandbox Quickstart

Use this stage ladder to identify exactly where a test integration stops. Do not switch to live mode until every applicable stage passes.

## Stage 1 — Configuration

Run the local setup checker relative to the installed skill root. In a repository checkout:

```bash
python skills/paymob-integration/scripts/paymob_setup_check.py
```

Resolve every `FAIL`. Review every `WARN`, especially Integration ID mode, callback reachability, and non-placeholder values. The checker never prints secrets.

The minimum configuration is listed in `credentials-and-integration-ids.md`, including the regional base URL and public HTTPS `APP_URL` required by the checker.

## Stage 2 — Intention

Create a payment attempt from an authenticated local order. The backend must derive amount, currency, items, mode, and Integration IDs from trusted storage.

Pass when:

- Paymob returns an intention ID and a fresh `client_secret`;
- the local attempt stores the opaque merchant reference and expected payment facts;
- no key or customer data appears in logs.

Common failures: `401` means Secret Key/auth-header trouble; `404 Integration ID` usually means account, region, or test/live mismatch; `400/422` means a required request field is missing or invalid.

## Stage 3 — Checkout

Launch Unified Checkout using the backend-generated URL and complete one supported sandbox payment from `test-credentials.md`.

Pass when the hosted checkout loads and Paymob accepts the test method. Do not infer final payment status from the browser redirect or SDK result.

## Stage 4 — Callback receipt

Use Paymob's official webhook testing tool or a controlled HTTPS development endpoint. Send only synthetic/test transactions.

Pass when the endpoint receives `POST` JSON and a query `hmac`, stays within request-size limits, and returns a controlled response. Do not log the raw body.

## Stage 5 — HMAC

Pass when the exact 20-field `transaction-hmac-fixture.json` vector verifies and any changed field, missing/null field, non-hex signature, wrong length, Unicode signature, or wrong secret fails closed without a `500`.

## Stage 6 — Business binding

Pass when the verified callback matches the stored attempt's amount, currency, Integration ID, owner/account, mode, and opaque merchant reference. A valid HMAC with any mismatch must be quarantined and must not update the order.

## Stage 7 — State and fulfillment

Pass when the provider event is unique on `obj.id`, the order uses an allowed compare-and-set transition, and exactly one fulfillment outbox record is created for a completed sale/capture. Pending, failure, auth-only, void, and refund events must not create new fulfillment.

## Stage 8 — Reconciliation

Run Transaction Inquiry for the test payment and apply the same binding and state-transition rules. Confirm that a missed callback can be reconciled without duplicating fulfillment.

## Exit criteria

- All applicable stages pass.
- Duplicate and concurrent callbacks are safe.
- Logs contain no raw callback, customer PII, client secret, token, or Paymob key.
- The live deployment uses separate, newly confirmed live keys and Integration IDs.
