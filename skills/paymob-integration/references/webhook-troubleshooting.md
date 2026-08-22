# Webhook Troubleshooting by Stage

Diagnose the earliest failing stage. Do not skip ahead or disable HMAC to make a test pass.

| Stage | Symptom | Check | Safe next action |
|---|---|---|---|
| Delivery | No callback | Public HTTPS URL, DNS/TLS, route, firewall, request limit | Use Paymob's webhook testing tool with synthetic data; inspect request metadata only |
| Parsing | `400` or `500` | JSON content type, body shape, `obj`, nested `order` and `source_data` | Reject malformed input with controlled `4xx`; do not mutate state |
| Signature | HMAC mismatch | Correct HMAC Secret, POST `body.obj`, exact 20 fields/order, lowercase booleans, 128 hex chars | Compare against the canonical fixture; never accept or log the supplied secret |
| Binding | Signed callback is quarantined | Amount, currency, Integration ID, owner/account, merchant reference, Paymob IDs | Compare with the stored attempt and investigate account/mode mismatch |
| Lifecycle | Paid-looking event did not fulfill | `pending`, `success`, `error_occured`, auth/capture/refund/void flags | Apply the classifier in `integration-safety.md`; do not override manually from redirect data |
| Persistence | Provider retries / duplicate processing | Unique `obj.id`, transaction boundary, compare-and-set, fulfillment outbox key | Treat duplicate events as `2xx` no-ops; fix failed atomic commit before acknowledging |
| Reconciliation | Local order remains pending | Transaction Inquiry result and stored attempt binding | Reconcile through the same state machine; do not key idempotency on the order ID |

## Redacted diagnostic record

Record only:

- internal trace ID;
- HMAC result (`valid`/`invalid`, never the signature);
- provider event ID and opaque attempt reference, hashed/truncated when appropriate;
- amount/currency, Integration ID, mode, and lifecycle classification;
- binding mismatch field names, not secret or customer values.

Never record the raw request body, full query URL, email, phone, billing address, saved-card token, client secret, auth token, API Key, Secret Key, or HMAC Secret.

## Escalation bundle

When escalation is necessary, provide timestamps, region, test/live mode, redacted request/response status, Paymob transaction/order IDs where policy permits, the failing stage, and a correlation/trace ID. Do not attach `.env` files or raw callbacks.
