# Paymob — Frontend (React / Next.js / Vue) + Unified Checkout

The frontend's only job is: call **your** backend to create the Intention, then send the customer to Paymob's **Unified Checkout** (or render the embedded Pixel SDK). The Public Key is the only Paymob credential allowed in the browser; the Secret Key / API Key / HMAC Secret must never reach the client.

## Golden rules

- **Never** create the Intention from the browser — that would require the Secret Key client-side. Always go through your backend (see the `code-*.md` for your stack).
- Send only an authenticated opaque `checkoutSessionId`/local order reference. The backend must load the order and derive amount, currency, items, account/mode, and Integration IDs from trusted storage; never trust cart totals or prices from the browser.
- Only the **Public Key** is safe in frontend code.
- The redirect/return page is **for UX only**. Payment status is decided by your backend's HMAC-verified callback, never by the return-page query params.

## Option A — Redirect to Unified Checkout (simplest, recommended)

Your backend returns a `checkout_url` (it builds `https://{base}/unifiedcheckout/?publicKey=...&clientSecret=...`). The frontend just navigates to it.

### React / plain JS

```jsx
async function startCheckout(checkoutSessionId) {
  const res = await fetch("/api/checkout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
    body: JSON.stringify({ checkoutSessionId }),
  });
  if (!res.ok) throw new Error("Checkout could not be created");
  const { checkoutUrl, checkoutAttemptToken } = await res.json();
  sessionStorage.setItem("paymobCheckoutAttempt", checkoutAttemptToken);
  window.location.href = checkoutUrl;   // hand off to Paymob's hosted page
}
```

### Next.js (App Router)

```tsx
"use client";
export default function PayButton({ checkoutSessionId }) {
  async function pay() {
    const res = await fetch("/api/checkout", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
      body: JSON.stringify({ checkoutSessionId }),
    });
    if (!res.ok) throw new Error("Checkout could not be created");
    const { checkoutUrl, checkoutAttemptToken } = await res.json();
    sessionStorage.setItem("paymobCheckoutAttempt", checkoutAttemptToken);
    window.location.href = checkoutUrl;
  }
  return <button onClick={pay}>Pay now</button>;
}
```

Implement `/api/checkout` as a Next.js Route Handler that calls `createIntention` from `code-nodejs.md` server-side (keeps the Secret Key on the server).

### Vue 3

```vue
<script setup>
async function pay(checkoutSessionId) {
  const res = await fetch("/api/checkout", {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
    body: JSON.stringify({ checkoutSessionId }),
  });
  if (!res.ok) throw new Error("Checkout could not be created");
  const { checkoutUrl, checkoutAttemptToken } = await res.json();
  sessionStorage.setItem("paymobCheckoutAttempt", checkoutAttemptToken);
  window.location.href = checkoutUrl;
}
</script>
<template><button @click="pay(checkoutSessionId)">Pay now</button></template>
```

### The return page

After payment, Paymob redirects the customer to your `redirection_url` with transaction params (incl. an `hmac`). Show a neutral "we're confirming your payment" state and **fetch the real status from your backend** (which knows the truth from the verified callback). Do not flip the order to "paid" based on these query params.

```jsx
// Ignore Paymob's unauthenticated success/order query parameters.
function PaymentComplete() {
  const attemptToken = sessionStorage.getItem("paymobCheckoutAttempt");
  const [status, setStatus] = useState("checking");
  useEffect(() => {
    if (!attemptToken) return setStatus("unknown");
    fetch("/api/payment-attempts/status", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": getCsrfToken() },
      body: JSON.stringify({ checkoutAttemptToken: attemptToken }),
    }) // backend enforces the current customer/tenant and returns minimal status
      .then(r => r.json()).then(d => setStatus(d.paid ? "paid" : "pending"));
  }, [attemptToken]);
  return <p>Payment status: {status}</p>;
}
```

## Option B — Embedded Pixel SDK (checkout inside your page)

When you want the payment form embedded rather than a full redirect. You still create the Intention on the backend and pass the `client_secret` + Public Key to the SDK.

```html
<script src="https://accept.paymob.com/unifiedcheckout/static/scripts/paymob-sdk.js"></script>
<div id="paymob-container"></div>
<script>
  // base + script path can change — confirm the current embed snippet in the live docs
  // (developers.paymob.com / wizard.paymob.com) before shipping.
  const paymob = Paymob.init({
    publicKey: "pk_test_xxxxxxxx",      // Public Key only — never the Secret Key
    clientSecret: CLIENT_SECRET_FROM_YOUR_BACKEND,
    elementId: "paymob-container",
    afterPaymentComplete: (result) => {
      // UI only — confirm real status from your backend callback
      window.location.href = "/payment/complete";
    },
    onPaymentCancel: () => console.log("cancelled"),
  });
</script>
```

> The embedded SDK's exact script URL, init options, and callback names are versioned by Paymob and can change. Pull the current embed snippet from `developers.paymob.com` (or the Integration Wizard's code lab) rather than relying on this sample verbatim — see `live-resources.md`.

## Per-region base URL

Swap `accept.paymob.com` for the merchant's region in any URL the frontend builds or receives:

| Region | Base |
|---|---|
| Egypt | `accept.paymob.com` |
| Oman | `oman.paymob.com` |
| KSA | `ksa.paymob.com` |
| UAE | `uae.paymob.com` |

(Ideally the frontend never hardcodes this — let the backend return the full `checkout_url`.)

The checkout and status endpoints require normal authentication, tenant/order ownership checks, rate limits, and CSRF protection when cookie-authenticated. Only the Paymob webhook route is exempt from CSRF.
