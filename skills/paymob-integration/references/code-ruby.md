# Paymob — Ruby / Rails

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

## Client (`lib/paymob.rb`) — net/http, no gems required

```ruby
require "net/http"
require "json"
require "openssl"
require "uri"

class Paymob
  def initialize
    bases = { "egypt" => "https://accept.paymob.com", "uae" => "https://uae.paymob.com",
              "ksa" => "https://ksa.paymob.com", "oman" => "https://oman.paymob.com" }
    region = ENV.fetch("PAYMOB_REGION").downcase
    mode = ENV.fetch("PAYMOB_MODE").downcase
    raise "Invalid Paymob region or mode" unless bases.key?(region) && %w[test live].include?(mode)
    @base = bases.fetch(region)
    raise "PAYMOB_BASE_URL does not match PAYMOB_REGION" unless ENV.fetch("PAYMOB_BASE_URL").chomp("/") == @base
    @secret = ENV.fetch("PAYMOB_SECRET_KEY")
    @public = ENV.fetch("PAYMOB_PUBLIC_KEY")
    @hmac   = ENV.fetch("PAYMOB_HMAC_SECRET")
    raise "Missing or placeholder Paymob configuration" if [@secret, @public, @hmac].any? { |value|
      value.empty? || value.match?(/xxxxx|changeme|replace_me|your_|example/i)
    }
    [@secret, @public].each do |credential|
      match = credential.match(/(?:^|_)(test|live)_/i)
      key_mode = match && match[1].downcase
      raise "Paymob key mode mismatch" if key_mode && key_mode != mode
    end
  end

  def create_intention(amount_cents:, currency:, payment_methods:, special_reference:, customer:, billing_country:, items: [])
    payload = {
      amount: amount_cents,
      currency: currency,
      payment_methods: payment_methods,
      items: items,
      special_reference: special_reference,
      billing_data: {
        first_name: customer[:first_name], last_name: customer[:last_name],
        email: customer[:email], phone_number: customer[:phone], # REQUIRED
        apartment: "NA", floor: "NA", street: "NA", building: "NA",
        shipping_method: "NA", postal_code: "NA", city: "NA", state: "NA", country: billing_country
      },
      customer: { first_name: customer[:first_name], last_name: customer[:last_name], email: customer[:email] },
      notification_url: "#{ENV['APP_URL']}/api/paymob/webhook",
      redirection_url: "#{ENV['APP_URL']}/payment/complete"
    }
    res = post("/v1/intention/", payload)
    { id: res["id"], client_secret: res["client_secret"] }
  end

  def checkout_url(client_secret)
    "#{@base}/unifiedcheckout/?publicKey=#{@public}&clientSecret=#{client_secret}"
  end

  def verify_transaction_post_hmac(obj, received_hmac)
    return false unless received_hmac.to_s.match?(/\A[0-9a-fA-F]{128}\z/)
    fields = [
      obj.fetch("amount_cents"), obj.fetch("created_at"), obj.fetch("currency"), obj.fetch("error_occured"),
      obj.fetch("has_parent_transaction"), obj.fetch("id"), obj.fetch("integration_id"), obj.fetch("is_3d_secure"),
      obj.fetch("is_auth"), obj.fetch("is_capture"), obj.fetch("is_refunded"), obj.fetch("is_standalone_payment"),
      obj.fetch("is_voided"), obj.fetch("order").fetch("id"), obj.fetch("owner"), obj.fetch("pending"),
      obj.fetch("source_data").fetch("pan"), obj.fetch("source_data").fetch("sub_type"),
      obj.fetch("source_data").fetch("type"), obj.fetch("success")
    ]
    return false if fields.any?(&:nil?)
    concat = fields.map { |v| bool_str(v) }.join
    computed = [OpenSSL::HMAC.hexdigest("SHA512", @hmac, concat)].pack("H*")
    received = [received_hmac].pack("H*")
    OpenSSL.fixed_length_secure_compare(computed, received)
  rescue KeyError, TypeError
    false
  end

  private

  # Ruby's true.to_s is "true" already — but be explicit to avoid surprises with nil.
  def bool_str(v)
    return "true" if v == true
    return "false" if v == false
    v.to_s
  end

  def post(path, body)
    uri = URI("#{@base}#{path}")
    http = Net::HTTP.new(uri.host, uri.port); http.use_ssl = (uri.scheme == "https")
    req = Net::HTTP::Post.new(uri)
    req["Authorization"] = "Token #{@secret}"   # literal "Token", not "Bearer"
    req["Content-Type"]  = "application/json"
    req.body = body.to_json
    res = http.request(req)
    raise "Paymob error #{res.code}: #{res.body}" if res.code.to_i >= 400
    JSON.parse(res.body)
  end
end
```

Keep refund/void/capture out of the basic checkout client. If required, implement the controlled application service described in `advanced-features.md` and `integration-safety.md`.

## Rails controller

```ruby
# config/routes.rb
#   post "/api/checkout",        to: "payments#checkout"
#   post "/api/paymob/webhook",  to: "payments#webhook"

class PaymentsController < ApplicationController
  skip_before_action :verify_authenticity_token, only: [:webhook]
  before_action :authenticate_user!, only: [:checkout]

  def checkout
    unless request.media_type == "application/json"
      return render json: { error: "JSON required" }, status: :unsupported_media_type
    end
    checkout_session_id = params[:checkoutSessionId]
    unless checkout_session_id.is_a?(String) && checkout_session_id.present? && checkout_session_id.bytesize <= 200
      return render json: { error: "Invalid checkout session" }, status: :bad_request
    end
    paymob = Paymob.new
    attempt = CheckoutStore.prepare_attempt!(
      checkout_session_id: checkout_session_id,
      customer_id: current_user.id
    )
    intention = paymob.create_intention(
      amount_cents: attempt.amount_cents,
      currency: attempt.currency,
      payment_methods: attempt.payment_methods,
      special_reference: attempt.reference,
      customer: attempt.customer,
      billing_country: attempt.billing_country,
      items: attempt.items
    )
    CheckoutStore.attach_paymob_intention!(attempt.id, intention[:id])
    render json: {
      checkout_url: paymob.checkout_url(intention[:client_secret]),
      checkoutAttemptToken: attempt.status_token
    }
  end

  def webhook
    unless request.media_type == "application/json"
      return render json: { error: "JSON required" }, status: :unsupported_media_type
    end
    if request.content_length.to_i > 65_536
      return render json: { error: "Payload too large" }, status: :payload_too_large
    end
    paymob   = Paymob.new
    obj_params = params[:obj]
    unless obj_params.is_a?(ActionController::Parameters)
      return render json: { error: "Invalid obj" }, status: :bad_request
    end
    obj = obj_params.to_unsafe_h
    received = params[:hmac]
    unless received.is_a?(String)
      return render json: { error: "One HMAC value required" }, status: :bad_request
    end
    unless paymob.verify_transaction_post_hmac(obj, received)
      return render json: { error: "Invalid HMAC" }, status: :unauthorized
    end
    PaymobPaymentEventStore.record_verified_event!(
      provider_event_id: obj["id"].to_s,
      paymob_order_id: obj.dig("order", "id").to_s,
      merchant_order_id: obj.dig("order", "merchant_order_id").to_s,
      amount_cents: obj["amount_cents"].to_i,
      currency: obj["currency"].to_s,
      integration_id: obj["integration_id"].to_i,
      owner: obj["owner"].to_s,
      classification: PaymobTransactionState.classify(obj)
    )
    render json: { received: true }
  end
end
```

The adapters and `PaymobTransactionState.classify` are required application boundaries. Follow `integration-safety.md`: bind the verified event to the stored attempt, commit a binding mismatch as a quarantined no-op, insert a UNIQUE provider event keyed by `obj["id"]`, apply the ordered lifecycle classifier and compare-and-set, and insert a UNIQUE fulfillment outbox row only for a completed sale/capture. The bang method must raise only when the atomic persistence transaction fails so Rails returns non-2xx. Enforce the same 64 KiB webhook limit at the web server/proxy for chunked requests. Return status through an authenticated, ownership-checked endpoint using `status_token`.

## Gotchas

- Header `Authorization: Token <secret>` (not Bearer). Derive amount/items/currency/Integration IDs server-side. `phone_number` is required.
- Booleans concatenate as `true`/`false` (Ruby's `to_s` already does this; `bool_str` guards `nil`).
- Use `OpenSSL.fixed_length_secure_compare` (timing-safe). Verify HMAC before trusting `success`; never trust redirect params. `client_secret` is single-use.
- Validate the exact Paymob origin before attaching the Secret Key, and emit redacted structured logs only.
