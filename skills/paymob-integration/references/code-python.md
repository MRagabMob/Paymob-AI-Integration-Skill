# Paymob — Python (Django / Flask / FastAPI)

Clean, correct reference (Intention API + Unified Checkout + HMAC-verified webhook). Read `intention-api.md` and `hmac-verification.md` alongside this.

## Environment

```env
PAYMOB_REGION=egypt
PAYMOB_MODE=test
PAYMOB_BASE_URL=https://accept.paymob.com
PAYMOB_SECRET_KEY=sk_test_xxxxxxxx
PAYMOB_PUBLIC_KEY=pk_test_xxxxxxxx
PAYMOB_HMAC_SECRET=your_hmac_secret
PAYMOB_INTEGRATION_ID_CARD=123456
APP_URL=https://yoursite.com
```

```bash
pip install requests python-dotenv
```

## Client (`paymob.py`)

```python
import os, hashlib, hmac, re
import requests


class PaymobClient:
    def __init__(self):
        bases = {"egypt": "https://accept.paymob.com", "uae": "https://uae.paymob.com",
                 "ksa": "https://ksa.paymob.com", "oman": "https://oman.paymob.com"}
        region = os.environ.get("PAYMOB_REGION", "").lower()
        mode = os.environ.get("PAYMOB_MODE", "").lower()
        if region not in bases or mode not in {"test", "live"}:
            raise RuntimeError("Invalid Paymob region or mode")
        self.base = bases[region]
        if os.environ.get("PAYMOB_BASE_URL", "").rstrip("/") != self.base:
            raise RuntimeError("PAYMOB_BASE_URL does not match PAYMOB_REGION")
        self.secret = os.environ["PAYMOB_SECRET_KEY"]
        self.public = os.environ["PAYMOB_PUBLIC_KEY"]
        self.hmac_secret = os.environ["PAYMOB_HMAC_SECRET"]
        if not all(v and not re.search(r"xxxxx|changeme|replace_me|your_|example", v, re.I)
                   for v in (self.secret, self.public, self.hmac_secret)):
            raise RuntimeError("Missing or placeholder Paymob configuration")
        for value in (self.secret, self.public):
            found = re.search(r"(?:^|_)(test|live)_", value, re.I)
            if found and found.group(1).lower() != mode:
                raise RuntimeError("Paymob key mode mismatch")
        self.s = requests.Session()
        self.s.headers.update({
            "Authorization": f"Token {self.secret}",   # literal "Token", not "Bearer"
            "Content-Type": "application/json",
        })

    def create_intention(self, *, amount_cents, currency, payment_methods,
                         special_reference, customer, billing_country, items=None) -> dict:
        payload = {
            "amount": amount_cents,
            "currency": currency,
            "payment_methods": payment_methods,
            "items": items or [],
            "special_reference": special_reference,
            "billing_data": {
                "first_name": customer["first_name"],
                "last_name": customer["last_name"],
                "email": customer["email"],
                "phone_number": customer["phone"],     # REQUIRED
                "apartment": "NA", "floor": "NA", "street": "NA", "building": "NA",
                "shipping_method": "NA", "postal_code": "NA", "city": "NA",
                "state": "NA", "country": billing_country,
            },
            "customer": {
                "first_name": customer["first_name"],
                "last_name": customer["last_name"],
                "email": customer["email"],
            },
            "notification_url": f"{os.environ['APP_URL']}/api/paymob/webhook",
            "redirection_url": f"{os.environ['APP_URL']}/payment/complete",
        }
        r = self.s.post(f"{self.base}/v1/intention/", json=payload)
        r.raise_for_status()
        d = r.json()
        return {"id": d["id"], "client_secret": d["client_secret"]}

    def checkout_url(self, client_secret: str) -> str:
        return f"{self.base}/unifiedcheckout/?publicKey={self.public}&clientSecret={client_secret}"

    def verify_transaction_post_hmac(self, obj: dict, received_hmac: str) -> bool:
        if not re.fullmatch(r"[0-9a-fA-F]{128}", received_hmac or ""):
            return False
        try:
            fields = [
                obj["amount_cents"], obj["created_at"], obj["currency"], obj["error_occured"],
                obj["has_parent_transaction"], obj["id"], obj["integration_id"], obj["is_3d_secure"],
                obj["is_auth"], obj["is_capture"], obj["is_refunded"], obj["is_standalone_payment"],
                obj["is_voided"], obj["order"]["id"], obj["owner"], obj["pending"],
                obj["source_data"]["pan"], obj["source_data"]["sub_type"],
                obj["source_data"]["type"], obj["success"],
            ]
            if any(value is None for value in fields):
                return False
            concat = "".join(_paymob_str(f) for f in fields)
            computed = hmac.new(self.hmac_secret.encode(), concat.encode(), hashlib.sha512).digest()
            return hmac.compare_digest(computed, bytes.fromhex(received_hmac))
        except (KeyError, TypeError, ValueError):
            return False


def _paymob_str(v) -> str:
    # Python's str(True) is "True"; Paymob expects JSON-style "true"/"false"
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
```

> **Note the boolean fix:** Paymob concatenates booleans as lowercase `true`/`false`. Naive `str(True)` yields `"True"` and silently breaks HMAC. `_paymob_str` handles it.

Keep refund/void/capture out of the basic checkout client. If required, implement the controlled application service described in `advanced-features.md` and `integration-safety.md`.

## Django view

```python
import json
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from .paymob import PaymobClient
from .payment_store import checkout_store, payment_store
from .payment_state import classify_paymob_transaction

paymob = PaymobClient()

@login_required
@require_POST
def create_checkout(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "JSON required"}, status=415)
    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    checkout_session_id = data.get("checkoutSessionId") if isinstance(data, dict) else None
    if not isinstance(checkout_session_id, str) or not checkout_session_id or len(checkout_session_id) > 200:
        return JsonResponse({"error": "Invalid checkout session"}, status=400)
    attempt = checkout_store.prepare_attempt(
        checkout_session_id=checkout_session_id,
        customer_id=request.user.id,
    )
    intention = paymob.create_intention(
        amount_cents=attempt.amount_cents,
        currency=attempt.currency,
        payment_methods=attempt.payment_methods,
        special_reference=attempt.reference,
        customer=attempt.customer,
        billing_country=attempt.billing_country,
        items=attempt.items,
    )
    checkout_store.attach_paymob_intention(attempt.id, intention["id"])
    return JsonResponse({
        "checkout_url": paymob.checkout_url(intention["client_secret"]),
        "checkoutAttemptToken": attempt.status_token,
    })

@csrf_exempt
@require_POST
def paymob_webhook(request):
    if request.content_type != "application/json":
        return JsonResponse({"error": "JSON required"}, status=415)
    if len(request.body) > 65536:
        return JsonResponse({"error": "Payload too large"}, status=413)
    try:
        body = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    if not isinstance(body, dict):
        return JsonResponse({"error": "Invalid payload"}, status=400)
    obj = body.get("obj", {})
    if not isinstance(obj, dict):
        return JsonResponse({"error": "Invalid obj"}, status=400)
    received_values = request.GET.getlist("hmac")
    if len(received_values) != 1:
        return JsonResponse({"error": "One HMAC value required"}, status=400)
    received = received_values[0]
    if not paymob.verify_transaction_post_hmac(obj, received):
        return JsonResponse({"error": "Invalid HMAC"}, status=401)
    payment_store.record_verified_event(
        provider_event_id=str(obj["id"]),
        paymob_order_id=str(obj["order"]["id"]),
        merchant_order_id=str(obj["order"].get("merchant_order_id", "")),
        amount_cents=int(obj["amount_cents"]),
        currency=str(obj["currency"]),
        integration_id=int(obj["integration_id"]),
        owner=str(obj["owner"]),
        classification=classify_paymob_transaction(obj),
    )
    return JsonResponse({"received": True})
```

The adapters and `classify_paymob_transaction` are required application boundaries. Follow `integration-safety.md`: bind the verified event to the stored attempt, commit a binding mismatch as a quarantined no-op, insert a UNIQUE provider event keyed by `obj["id"]`, apply the ordered lifecycle classifier and compare-and-set, and insert a UNIQUE fulfillment outbox row only for a completed sale/capture. Raise only when the atomic persistence transaction fails. Keep checkout CSRF-protected; exempt only the webhook. Return status through an authenticated, ownership-checked endpoint using `status_token`.

## Flask / FastAPI

Identical client; only the request plumbing differs:

```python
# Flask
values = request.args.getlist("hmac")
received = values[0] if len(values) == 1 else None
body = request.get_json(silent=True)
# FastAPI
values = request.query_params.getlist("hmac")
received = values[0] if len(values) == 1 else None
body = await request.json()
```

In both, return a controlled `400` when there is not exactly one HMAC value or JSON parsing/schema validation fails. Then pull `obj = body["obj"]`, call `paymob.verify_transaction_post_hmac(obj, received)`, and apply the same atomic unique-event + compare-and-set + transactional-outbox pattern before fulfillment.

## Gotchas

- `Authorization: Token <secret>` (not Bearer). Derive amount/items/currency/Integration IDs server-side. `billing_data.phone_number` is required.
- Concatenate booleans as `true`/`false` (see `_paymob_str`).
- Verify HMAC before trusting `success`; never trust redirect params. `client_secret` is single-use.
- Validate the exact Paymob origin before attaching the Secret Key, and emit redacted structured logs only.
