# Paymob — PHP / Laravel

Clean, correct reference (Intention API + Unified Checkout + HMAC-verified webhook). Read `intention-api.md` and `hmac-verification.md` alongside this.

## Environment (`.env`)

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

## Plain PHP client (`Paymob.php`)

Uses cURL — no dependencies. (In Laravel, swap cURL for the `Http` facade; logic is identical.)

```php
<?php

class Paymob
{
    private string $base;
    private string $secret;
    private string $public;
    private string $hmacSecret;

    public function __construct()
    {
        $region = strtolower($this->requiredEnv('PAYMOB_REGION'));
        $mode = strtolower($this->requiredEnv('PAYMOB_MODE'));
        $bases = ['egypt' => 'https://accept.paymob.com', 'uae' => 'https://uae.paymob.com',
                  'ksa' => 'https://ksa.paymob.com', 'oman' => 'https://oman.paymob.com'];
        if (!isset($bases[$region]) || !in_array($mode, ['test', 'live'], true)) {
            throw new RuntimeException('Invalid Paymob region or mode');
        }
        $this->base = $bases[$region];
        if (rtrim($this->requiredEnv('PAYMOB_BASE_URL'), '/') !== $this->base) {
            throw new RuntimeException('PAYMOB_BASE_URL does not match PAYMOB_REGION');
        }
        $this->secret     = $this->requiredEnv('PAYMOB_SECRET_KEY');
        $this->public     = $this->requiredEnv('PAYMOB_PUBLIC_KEY');
        $this->hmacSecret = $this->requiredEnv('PAYMOB_HMAC_SECRET');
        foreach ([$this->secret, $this->public] as $credential) {
            if (preg_match('/(?:^|_)(test|live)_/i', $credential, $match)
                && strtolower($match[1]) !== $mode) {
                throw new RuntimeException('Paymob key mode mismatch');
            }
        }
    }

    public function createIntention(array $args): array
    {
        $payload = [
            'amount'          => $args['amount_cents'],
            'currency'        => $args['currency'],
            'payment_methods' => $args['payment_methods'],
            'items'           => $args['items'] ?? [],
            'special_reference' => $args['special_reference'],
            'billing_data'    => [
                'first_name'   => $args['customer']['first_name'],
                'last_name'    => $args['customer']['last_name'],
                'email'        => $args['customer']['email'],
                'phone_number' => $args['customer']['phone'],   // REQUIRED
                'apartment' => 'NA', 'floor' => 'NA', 'street' => 'NA', 'building' => 'NA',
                'shipping_method' => 'NA', 'postal_code' => 'NA', 'city' => 'NA',
                'state' => 'NA', 'country' => $args['billing_country'],
            ],
            'customer' => [
                'first_name' => $args['customer']['first_name'],
                'last_name'  => $args['customer']['last_name'],
                'email'      => $args['customer']['email'],
            ],
            'notification_url' => getenv('APP_URL') . '/api/paymob/webhook',
            'redirection_url'  => getenv('APP_URL') . '/payment/complete',
        ];

        $res = $this->post('/v1/intention/', $payload);
        return ['id' => $res['id'], 'client_secret' => $res['client_secret']];
    }

    public function checkoutUrl(string $clientSecret): string
    {
        return "{$this->base}/unifiedcheckout/?publicKey={$this->public}&clientSecret={$clientSecret}";
    }

    public function verifyTransactionPostHmac(array $obj, string $receivedHmac): bool
    {
        if (!preg_match('/\A[0-9a-fA-F]{128}\z/', $receivedHmac)) return false;
        $top = ['amount_cents', 'created_at', 'currency', 'error_occured',
                'has_parent_transaction', 'id', 'integration_id', 'is_3d_secure',
                'is_auth', 'is_capture', 'is_refunded', 'is_standalone_payment',
                'is_voided', 'owner', 'pending', 'success'];
        foreach ($top as $key) if (!array_key_exists($key, $obj)) return false;
        if (!is_array($obj['order'] ?? null) || !array_key_exists('id', $obj['order'])) return false;
        if (!is_array($obj['source_data'] ?? null)) return false;
        foreach (['pan', 'sub_type', 'type'] as $key) {
            if (!array_key_exists($key, $obj['source_data'])) return false;
        }
        try {
            $fields = [
                $obj['amount_cents'], $obj['created_at'], $obj['currency'], $obj['error_occured'],
                $obj['has_parent_transaction'], $obj['id'], $obj['integration_id'], $obj['is_3d_secure'],
                $obj['is_auth'], $obj['is_capture'], $obj['is_refunded'], $obj['is_standalone_payment'],
                $obj['is_voided'], $obj['order']['id'], $obj['owner'], $obj['pending'],
                $obj['source_data']['pan'], $obj['source_data']['sub_type'],
                $obj['source_data']['type'], $obj['success'],
            ];
            if (in_array(null, $fields, true)) return false;
            $concat   = implode('', array_map([$this, 'boolStr'], $fields));
            $computed = hash_hmac('sha512', $concat, $this->hmacSecret, true);
            $received = hex2bin($receivedHmac);
            return $received !== false && hash_equals($computed, $received);
        } catch (Throwable) {
            return false;
        }
    }

    /** Paymob concatenates booleans as lowercase true/false; PHP's (string)true is "1". */
    private function boolStr($v): string
    {
        if (is_bool($v)) return $v ? 'true' : 'false';
        return (string) $v;
    }

    private function requiredEnv(string $name): string
    {
        $value = getenv($name);
        if (!is_string($value) || trim($value) === '' || preg_match('/xxxxx|changeme|replace_me|your_|example/i', $value)) {
            throw new RuntimeException("Missing or placeholder $name");
        }
        return $value;
    }

    private function post(string $path, array $body): array
    {
        $ch = curl_init($this->base . $path);
        curl_setopt_array($ch, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_POST           => true,
            CURLOPT_POSTFIELDS     => json_encode($body),
            CURLOPT_HTTPHEADER     => [
                'Authorization: Token ' . $this->secret,   // literal "Token", not "Bearer"
                'Content-Type: application/json',
            ],
        ]);
        $out  = curl_exec($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        curl_close($ch);
        $data = json_decode($out, true) ?? [];
        if ($code >= 400) {
            throw new RuntimeException("Paymob error $code: $out");
        }
        return $data;
    }
}
```

> **Boolean fix:** PHP casts `true` to `"1"`, but Paymob's HMAC expects `"true"`/`"false"`. Use `boolStr()` (above) instead of plain `(string)` when concatenating, or HMAC verification silently fails.

Keep refund/void/capture out of the basic checkout client. If required, implement the controlled application service described in `advanced-features.md` and `integration-safety.md`.

## Laravel checkout and webhook routes

```php
// routes/web.php  (or api.php)
use Illuminate\Http\Request;
use App\Contracts\CheckoutStore;
use App\Contracts\PaymobPaymentEventStore;
use App\Support\PaymobTransactionState;

Route::post('/api/checkout', function (Request $request) {
    $request->validate(['checkoutSessionId' => ['required', 'string', 'max:200']]);
    $attempt = app(CheckoutStore::class)->prepareAttempt(
        checkoutSessionId: $request->string('checkoutSessionId')->toString(),
        customerId: (string) $request->user()->getAuthIdentifier(),
    );
    $paymob = new Paymob();
    $intention = $paymob->createIntention([
        'amount_cents' => $attempt->amountCents,
        'currency' => $attempt->currency,
        'payment_methods' => $attempt->paymentMethods,
        'special_reference' => $attempt->reference,
        'customer' => $attempt->customer,
        'billing_country' => $attempt->billingCountry,
        'items' => $attempt->items,
    ]);
    app(CheckoutStore::class)->attachPaymobIntention($attempt->id, $intention['id']);
    return response()->json([
        'checkout_url' => $paymob->checkoutUrl($intention['client_secret']),
        'checkoutAttemptToken' => $attempt->statusToken,
    ]);
})->middleware('auth');

Route::post('/api/paymob/webhook', function (Request $request) {
    if (! $request->isJson()) {
        return response()->json(['error' => 'JSON required'], 415);
    }
    if ((int) $request->server('CONTENT_LENGTH', 0) > 65536) {
        return response()->json(['error' => 'Payload too large'], 413);
    }
    $paymob   = new Paymob();
    $obj      = $request->input('obj', []);
    if (!is_array($obj)) {
        return response()->json(['error' => 'Invalid obj'], 400);
    }
    $received = $request->query('hmac');
    if (!is_string($received)) {
        return response()->json(['error' => 'One HMAC value required'], 400);
    }

    if (empty($obj) || ! $paymob->verifyTransactionPostHmac($obj, $received)) {
        return response()->json(['error' => 'Invalid HMAC'], 401);
    }
    app(PaymobPaymentEventStore::class)->recordVerifiedEvent(
        providerEventId: (string) $obj['id'],
        paymobOrderId: (string) $obj['order']['id'],
        merchantOrderId: (string) ($obj['order']['merchant_order_id'] ?? ''),
        amountCents: (int) $obj['amount_cents'],
        currency: (string) $obj['currency'],
        integrationId: (int) $obj['integration_id'],
        owner: (string) $obj['owner'],
        classification: PaymobTransactionState::classify($obj),
    );
    return response()->json(['received' => true]);  // 200 stops Paymob retries
});
```

The adapters and `PaymobTransactionState::classify` are required application boundaries. Follow `integration-safety.md`: bind the verified event to the stored attempt, commit a binding mismatch as a quarantined no-op, insert a UNIQUE provider event keyed by `$obj['id']`, apply the ordered lifecycle classifier and compare-and-set, and insert a UNIQUE fulfillment outbox row only for a completed sale/capture. Throw only when the atomic persistence transaction fails. Return status through an authenticated, ownership-checked endpoint using `statusToken`.

Put checkout in the session-authenticated web route group. Exclude only the Paymob webhook route from CSRF protection, and enforce the same 64 KiB limit at the web server/proxy for chunked requests. Keep checkout and status routes authenticated and CSRF-protected.

## Gotchas

- Header `Authorization: Token <secret>` (not Bearer). Derive amount/items/currency/Integration IDs server-side. `phone_number` is required.
- Use `boolStr()` so booleans concatenate as `true`/`false` for HMAC.
- Always `hash_equals()` (timing-safe). Verify HMAC before trusting `success`; never trust redirect params. `client_secret` is single-use.
- Validate the exact Paymob origin before attaching the Secret Key, and emit redacted structured logs only.
