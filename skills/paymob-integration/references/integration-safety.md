# Payment Integrity and Application Safety

Read this file before generating custom checkout, webhook, reconciliation, or post-payment code. HMAC authentication is necessary, but it does not prove that the transaction matches the merchant's intended order.

## Contents

- Trusted checkout contract
- Stored payment attempt
- Webhook processing order
- Transaction state classification
- Atomic persistence and fulfillment
- Route, configuration, and logging controls
- Financial writes

## Trusted checkout contract

Accept only an authenticated, opaque `checkout_session_id` or local order ID from the browser. Never accept a browser-supplied amount, currency, Integration ID, item price, fulfillment target, or merchant/tenant ID as authoritative.

On the server:

1. Authenticate the customer and authorize access to the checkout session/order.
2. Load and lock the current order from trusted storage.
3. Recalculate the total from server-side product, tax, discount, and shipping data.
4. Select currency, region, Paymob account, mode, and allowed Integration IDs from server configuration.
5. Create a unique payment-attempt record and an opaque `special_reference` before calling Paymob.
6. Send only those trusted values to the Intention API.
7. Store Paymob's returned intention/order identifiers against the attempt.

Do not reuse the local order ID as a public bearer credential. The return page should use an authenticated session or an opaque checkout-attempt token, and its status endpoint must enforce customer/tenant ownership.

## Stored payment attempt

Persist at least:

- local attempt ID and opaque `special_reference`;
- customer/tenant and local order IDs;
- expected amount in smallest units and currency;
- allowed Integration ID and expected Paymob owner/account;
- region and test/live mode;
- Paymob intention/order ID when available;
- lifecycle state and timestamps.

Never store a Secret Key, API Key, HMAC Secret, or complete callback body in this record.

## Webhook processing order

Process callbacks in this order:

1. Enforce HTTPS, request-size limits, `POST`, JSON content type, and a short timeout.
2. Parse JSON and validate the required transaction schema without changing state.
3. Require the query `hmac` to be exactly 128 ASCII hexadecimal characters.
4. Calculate the documented 20-field SHA-512 HMAC and compare the 64 decoded bytes timing-safely.
5. Insert `obj.id` under a database unique constraint.
6. Resolve the stored attempt by the callback merchant reference.
7. Require exact matches for amount, currency, allowed Integration ID, Paymob owner/account, region/mode, and stored Paymob identifiers.
8. Classify the transaction state and apply only an allowed compare-and-set transition.
9. Insert a uniquely keyed fulfillment outbox item only for a completed sale/capture.
10. Commit, then return `2xx`. Let an outbox worker perform fulfillment.

Quarantine a validly signed callback that fails business binding. Record a redacted security event and do not mark the order paid.

## Transaction state classification

Do not equate `success == true && pending == false` with fulfillment.

| Condition | Local classification | Fulfill? |
|---|---|---|
| `pending == true` | pending | No |
| `is_refunded == true` | refunded/partially refunded | No new fulfillment |
| `is_voided == true` | voided | No |
| `error_occured == true` or `success != true` | failed | No |
| `is_auth == true` and `is_capture != true` | authorized | No |
| successful capture (`is_capture == true`) | paid/captured | Yes, once |
| successful immediate sale with no auth hold | paid | Yes, once |

Implement the checks in that order. In pseudocode:

```text
if pending: pending
else if refunded: refunded
else if voided: voided
else if error or not successful: failed
else if auth and not captured: authorized
else if captured: paid/captured
else: paid
```

Confirm any product-specific or region-specific flag behavior against the current Paymob docs before shipping. Handle duplicate and out-of-order events through the same state machine; never move a terminal refunded/voided state backward to paid.

## Atomic persistence and fulfillment

Use separate identities for separate purposes:

- `obj.id`: unique Paymob provider-event/transaction key;
- `special_reference` / merchant order ID: correlation to the stored attempt;
- local order ID: business order identity;
- fulfillment outbox key: one per local business fulfillment.

One order may have multiple payment attempts and multiple Paymob transaction IDs. Record each provider event once, but create no more than one fulfillment action for the business order. A losing compare-and-set or duplicate insert is a successful no-op.

Reconciliation observations must use the same binding and transition rules. Correlation IDs are not idempotency keys.

## Route, configuration, and logging controls

- Protect checkout and order-status routes with authentication, tenant/order ownership checks, rate limits, and CSRF protection when cookie-authenticated. Exempt only the Paymob webhook route from CSRF.
- Derive the Paymob origin from a region enum. Allow only the exact HTTPS origins documented in `intention-api.md`; reject custom ports, userinfo, paths, and cross-origin redirects before attaching `Authorization`.
- Fail startup on missing, blank, or placeholder secrets, invalid mode, or contradictory key modes.
- Make `PAYMOB_REGION`, `PAYMOB_MODE`, currency, billing country, and Integration IDs explicit. Do not silently deploy Egypt defaults for another market.
- Log only allowlisted fields after validation: internal trace ID, provider event ID, opaque attempt reference, verification result, classification, amount/currency, Integration ID, and mode. Hash or truncate identifiers where possible.
- Never log raw callbacks, query strings containing tokens, customer email/phone/address, full PAN metadata, saved-card tokens, API/auth tokens, client secrets, or Paymob keys.

## Financial writes

Application code for refund, void, capture, saved-card charge, or other consequential writes must enforce server-side RBAC, tenant ownership, current transaction state, amount/currency limits, a reason and actor audit record, and a unique operation fingerprint. After a timeout or ambiguous response, inquire by the same transaction/reference before any retry. Verify and persist the final remote state.

Do not expose the low-level write helpers directly as public application routes.
