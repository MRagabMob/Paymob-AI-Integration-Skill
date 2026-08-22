# Payment Methods and Feature Routing

Ask these questions before generating custom code:

1. Which market: Egypt, UAE, KSA, or Oman?
2. Which platform: Shopify, a supported e-commerce plugin, custom web/backend, or native mobile?
3. Is the payment one-time, recurring, or both?
4. Which methods are required: cards, wallets, Apple Pay, Google Pay, BNPL, kiosk, installments, or others?
5. Are saved cards, delayed capture, refunds/voids, split payments, or convenience fees required?
6. Is the goal sandbox testing, live launch, troubleshooting, or reconciliation?

## Route by need

| Need | Route |
|---|---|
| Standard Shopify checkout | Read `shopify-apps.md`; install the matching Paymob app |
| WooCommerce/Magento/Odoo/other supported platform | Prefer Paymob's official plugin |
| Custom one-time web checkout | Intention API + Unified Checkout + verified webhook |
| Native mobile checkout | Backend Intention + current mobile SDK + verified webhook |
| Recurring payments | Read the subscription section of `advanced-features.md` before generating code |
| Saved cards / CIT / MIT | Read card-token HMAC and saved-card controls in `advanced-features.md` |
| Auth then capture | Use the explicit lifecycle state machine; auth-only must not fulfill |
| Refund, void, or capture | Require application RBAC, tenant ownership, audit, reconciliation, and current authorization |
| Pending/missed callback | Use `transaction-inquiry.md` through the same binding/state rules |

Feature availability and sandbox support vary by account, payment method, and region. Confirm current enablement and Integration IDs in the dashboard, then verify volatile details against `live-resources.md`. Do not promise that a method or plan is enabled merely because this skill documents it.
