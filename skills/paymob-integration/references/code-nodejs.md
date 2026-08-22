# Paymob — Node.js / TypeScript (Express / NestJS)

Clean, correct reference implementation (Intention API + Unified Checkout + HMAC-verified webhook). Read `intention-api.md` and `hmac-verification.md` alongside this.

## Environment variables (`.env`)

```env
PAYMOB_REGION=egypt
PAYMOB_MODE=test
PAYMOB_BASE_URL=https://accept.paymob.com        # region base; oman./ksa./uae.paymob.com for others
PAYMOB_SECRET_KEY=sk_test_xxxxxxxx
PAYMOB_PUBLIC_KEY=pk_test_xxxxxxxx
PAYMOB_HMAC_SECRET=your_hmac_secret
PAYMOB_INTEGRATION_ID_CARD=123456                # one per enabled method
APP_URL=https://yoursite.com
```

## Install

```bash
npm install express axios dotenv     # crypto is built into Node
```

## Paymob client (`paymob.ts`)

```typescript
import axios from 'axios';
import crypto from 'crypto';

const SECRET = process.env.PAYMOB_SECRET_KEY!;
const PUBLIC = process.env.PAYMOB_PUBLIC_KEY!;
const HMAC_SECRET = process.env.PAYMOB_HMAC_SECRET!;

const BASE_BY_REGION = {
  egypt: 'https://accept.paymob.com', uae: 'https://uae.paymob.com',
  ksa: 'https://ksa.paymob.com', oman: 'https://oman.paymob.com',
} as const;
const REGION = String(process.env.PAYMOB_REGION ?? '').toLowerCase();
const MODE = String(process.env.PAYMOB_MODE ?? '').toLowerCase();
if (!(REGION in BASE_BY_REGION)) throw new Error('Invalid PAYMOB_REGION');
if (!['test', 'live'].includes(MODE)) throw new Error('Invalid PAYMOB_MODE');
const BASE = BASE_BY_REGION[REGION as keyof typeof BASE_BY_REGION];
const configuredBase = String(process.env.PAYMOB_BASE_URL ?? '').replace(/\/$/, '');
if (configuredBase !== BASE) throw new Error('PAYMOB_BASE_URL does not match PAYMOB_REGION');
if (![SECRET, PUBLIC, HMAC_SECRET].every(v => v && !/xxxxx|changeme|replace_me|your_|example/i.test(v))) {
  throw new Error('Missing or placeholder Paymob configuration');
}
for (const credential of [SECRET, PUBLIC]) {
  const keyMode = credential.match(/(?:^|_)(test|live)_/i)?.[1]?.toLowerCase();
  if (keyMode && keyMode !== MODE) throw new Error('Paymob key mode mismatch');
}

const api = axios.create({
  baseURL: BASE,
  headers: { Authorization: `Token ${SECRET}`, 'Content-Type': 'application/json' },
});

export interface IntentionInput {
  amountCents: number;
  currency: string;                       // e.g. 'EGP'
  paymentMethods: number[];               // Integration IDs
  specialReference: string;               // your own order id, echoed back as merchant_order_id
  customer: { firstName: string; lastName: string; email: string; phone: string };
  billingCountry: string;                 // server-derived ISO alpha-3 value, e.g. EGY/ARE/SAU/OMN
  items?: { name: string; amount: number; quantity: number; description?: string }[];
}

export async function createIntention(input: IntentionInput) {
  const { data } = await api.post('/v1/intention/', {
    amount: input.amountCents,
    currency: input.currency,
    payment_methods: input.paymentMethods,
    items: input.items ?? [],
    special_reference: input.specialReference,
    billing_data: {
      first_name: input.customer.firstName,
      last_name: input.customer.lastName,
      email: input.customer.email,
      phone_number: input.customer.phone,        // REQUIRED — omitting causes a 400
      apartment: 'NA', floor: 'NA', street: 'NA', building: 'NA',
      shipping_method: 'NA', postal_code: 'NA', city: 'NA', state: 'NA', country: input.billingCountry,
    },
    customer: {
      first_name: input.customer.firstName,
      last_name: input.customer.lastName,
      email: input.customer.email,
    },
    notification_url: `${process.env.APP_URL}/api/paymob/webhook`,
    redirection_url: `${process.env.APP_URL}/payment/complete`,
  });
  return { id: data.id, clientSecret: data.client_secret as string };
}

export function checkoutUrl(clientSecret: string) {
  return `${BASE}/unifiedcheckout/?publicKey=${PUBLIC}&clientSecret=${clientSecret}`;
}

// Transaction HMAC for POST webhook (20 fields from req.body.obj, in this exact order)
export function verifyTransactionPostHmac(obj: any, receivedHmac: string): boolean {
  if (!/^[a-f0-9]{128}$/i.test(receivedHmac)) return false;
  try {
    const fields = [
      obj.amount_cents, obj.created_at, obj.currency, obj.error_occured,
      obj.has_parent_transaction, obj.id, obj.integration_id, obj.is_3d_secure,
      obj.is_auth, obj.is_capture, obj.is_refunded, obj.is_standalone_payment,
      obj.is_voided, obj.order.id, obj.owner, obj.pending,
      obj.source_data.pan, obj.source_data.sub_type, obj.source_data.type, obj.success,
    ];
    if (fields.some(value => value == null)) return false;
    const computed = crypto.createHmac('sha512', HMAC_SECRET)
      .update(fields.map(String).join('')).digest();
    return crypto.timingSafeEqual(computed, Buffer.from(receivedHmac, 'hex'));
  } catch { return false; }
}
```

Keep refund/void/capture out of the basic checkout client. If required, implement the controlled application service described in `advanced-features.md` and `integration-safety.md`.

## Express routes (`routes.ts`)

```typescript
import express from 'express';
import { createIntention, checkoutUrl, verifyTransactionPostHmac } from './paymob';
import { checkoutStore, paymentEventStore } from './payment-store';
import { classifyPaymobTransaction } from './payment-state';
import { requireAuthenticatedCustomer } from './auth';

const router = express.Router();

router.post('/api/checkout', requireAuthenticatedCustomer, express.json({ limit: '16kb' }), async (req, res) => {
  if (!req.is('application/json')) return res.status(415).json({ error: 'JSON required' });
  const checkoutSessionId = req.body?.checkoutSessionId;
  if (typeof checkoutSessionId !== 'string' || !checkoutSessionId || checkoutSessionId.length > 200) {
    return res.status(400).json({ error: 'Invalid checkout session' });
  }
  // Adapter authenticates ownership, locks the order, calculates totals server-side,
  // selects account/mode/Integration IDs, and creates an opaque payment attempt.
  const attempt = await checkoutStore.prepareAttempt({
    checkoutSessionId,
    customerId: req.user.id,
  });
  const intention = await createIntention({
    amountCents: attempt.amountCents,
    currency: attempt.currency,
    paymentMethods: attempt.paymentMethods,
    specialReference: attempt.reference,
    customer: attempt.customer,
    billingCountry: attempt.billingCountry,
    items: attempt.items,
  });
  await checkoutStore.attachPaymobIntention(attempt.id, intention.id);
  res.json({
    checkoutUrl: checkoutUrl(intention.clientSecret),
    checkoutAttemptToken: attempt.statusToken,
  });
});

// Paymob POSTs the result here; hmac is a query param
router.post('/api/paymob/webhook', express.json({ limit: '64kb' }), async (req, res) => {
  if (!req.is('application/json')) return res.status(415).json({ error: 'JSON required' });
  const obj = req.body?.obj;
  if (typeof req.query.hmac !== 'string') {
    return res.status(400).json({ error: 'One HMAC value required' });
  }
  const receivedHmac = req.query.hmac;
  if (!obj || !verifyTransactionPostHmac(obj, receivedHmac)) {
    return res.status(401).json({ error: 'Invalid HMAC' });
  }
  try {
    await paymentEventStore.recordVerifiedEvent({
      providerEventId: String(obj.id),
      paymobOrderId: String(obj.order.id),
      merchantOrderId: String(obj.order.merchant_order_id),
      amountCents: Number(obj.amount_cents),
      currency: String(obj.currency),
      integrationId: Number(obj.integration_id),
      owner: String(obj.owner),
      classification: classifyPaymobTransaction(obj),
    });
  } catch {
    return res.status(503).json({ error: 'Payment persistence failed' });
  }
  res.status(200).json({ received: true });   // 200 even on ignore, to stop retries
});

export default router;
```

The adapters and `classifyPaymobTransaction` are required application boundaries. Follow `integration-safety.md`: bind the verified event to the stored attempt, commit a binding mismatch as a quarantined no-op, insert a UNIQUE provider event keyed by `obj.id`, apply the ordered lifecycle classifier and compare-and-set, and insert a UNIQUE fulfillment outbox row only for a completed sale/capture. Throw only when the atomic persistence transaction fails. Return status through an authenticated, ownership-checked endpoint using `statusToken`; never use redirect IDs as authorization.

## NestJS note

Wrap `createIntention`/`verifyTransactionPostHmac` in an injectable `PaymobService`, and read the raw `hmac` from `@Query('hmac')` in the webhook controller. The crypto logic is identical.

## Gotchas

- Header is `Token <secret>` — **not** `Bearer`.
- Derive amount/items/currency/Integration IDs server-side; the browser sends only `checkoutSessionId`.
- `billing_data.phone_number` is required.
- Verify HMAC **before** trusting `obj.success`. The redirect URL params are not authenticated — don't mark orders paid from them.
- `client_secret` is single-use — create a new Intention per attempt.
- Validate the exact Paymob origin before attaching the Secret Key, and emit redacted structured logs only.
