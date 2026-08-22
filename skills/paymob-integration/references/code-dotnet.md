# Paymob — .NET / C# (ASP.NET Core)

Clean, correct reference (Intention API + Unified Checkout + HMAC-verified webhook). Read `intention-api.md` and `hmac-verification.md` alongside this.

## Configuration (`appsettings.json` / env)

```json
{
  "Paymob": {
    "Region": "egypt",
    "Mode": "test",
    "BaseUrl": "https://accept.paymob.com",
    "SecretKey": "sk_test_xxxxxxxx",
    "PublicKey": "pk_test_xxxxxxxx",
    "HmacSecret": "your_hmac_secret",
    "IntegrationIdCard": 123456,
    "AppUrl": "https://yoursite.com"
  }
}
```

## Service (`PaymobService.cs`)

```csharp
using System.Collections.Generic;
using System.Linq;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

public class PaymobOptions
{
    public string Region { get; set; } = "";
    public string Mode { get; set; } = "";
    public string BaseUrl { get; set; } = "";
    public string SecretKey { get; set; } = "";
    public string PublicKey { get; set; } = "";
    public string HmacSecret { get; set; } = "";
    public int IntegrationIdCard { get; set; }
    public string AppUrl { get; set; } = "";
}

public record CustomerInfo(string FirstName, string LastName, string Email, string Phone);

public class PaymobService
{
    private readonly HttpClient _http;
    private readonly PaymobOptions _o;

    public PaymobService(HttpClient http, PaymobOptions options)
    {
        _o = options;
        _http = http;
        var bases = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase)
        {
            ["egypt"] = "https://accept.paymob.com", ["uae"] = "https://uae.paymob.com",
            ["ksa"] = "https://ksa.paymob.com", ["oman"] = "https://oman.paymob.com"
        };
        var mode = _o.Mode.ToLowerInvariant();
        if (!bases.TryGetValue(_o.Region, out var origin)
            || (mode != "test" && mode != "live"))
            throw new InvalidOperationException("Invalid Paymob region or mode");
        if (_o.BaseUrl.TrimEnd('/') != origin)
            throw new InvalidOperationException("PAYMOB_BASE_URL does not match PAYMOB_REGION");
        if (string.IsNullOrWhiteSpace(_o.SecretKey) || string.IsNullOrWhiteSpace(_o.PublicKey)
            || string.IsNullOrWhiteSpace(_o.HmacSecret)
            || new[] { _o.SecretKey, _o.PublicKey, _o.HmacSecret }.Any(value =>
                System.Text.RegularExpressions.Regex.IsMatch(value,
                    "xxxxx|changeme|replace_me|your_|example",
                    System.Text.RegularExpressions.RegexOptions.IgnoreCase)))
            throw new InvalidOperationException("Missing or placeholder Paymob configuration");
        foreach (var credential in new[] { _o.SecretKey, _o.PublicKey })
        {
            var match = System.Text.RegularExpressions.Regex.Match(
                credential, "(?:^|_)(test|live)_",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (match.Success && !string.Equals(match.Groups[1].Value, mode,
                    StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Paymob key mode mismatch");
        }
        _http.BaseAddress = new Uri(origin + "/");
        // literal scheme "Token", not "Bearer"
        _http.DefaultRequestHeaders.Add("Authorization", $"Token {_o.SecretKey}");
    }

    public async Task<(long Id, string ClientSecret)> CreateIntentionAsync(
        long amountCents, string currency, int[] paymentMethods,
        string specialReference, string billingCountry, CustomerInfo c)
    {
        var payload = new
        {
            amount = amountCents,
            currency,
            payment_methods = paymentMethods,
            items = Array.Empty<object>(),
            special_reference = specialReference,
            billing_data = new
            {
                first_name = c.FirstName, last_name = c.LastName, email = c.Email,
                phone_number = c.Phone,                 // REQUIRED
                apartment = "NA", floor = "NA", street = "NA", building = "NA",
                shipping_method = "NA", postal_code = "NA", city = "NA",
                state = "NA", country = billingCountry
            },
            customer = new { first_name = c.FirstName, last_name = c.LastName, email = c.Email },
            notification_url = $"{_o.AppUrl}/api/paymob/webhook",
            redirection_url = $"{_o.AppUrl}/payment/complete"
        };

        var resp = await _http.PostAsJsonAsync("v1/intention/", payload);
        resp.EnsureSuccessStatusCode();
        using var doc = JsonDocument.Parse(await resp.Content.ReadAsStringAsync());
        var root = doc.RootElement;
        return (root.GetProperty("id").GetInt64(),
                root.GetProperty("client_secret").GetString()!);
    }

    public string CheckoutUrl(string clientSecret) =>
        $"{_o.BaseUrl.TrimEnd('/')}/unifiedcheckout/?publicKey={_o.PublicKey}&clientSecret={clientSecret}";

    // Transaction HMAC for the POST webhook. `obj` is the parsed body.obj element.
    public bool VerifyTransactionPostHmac(JsonElement obj, string receivedHmac)
    {
        if (string.IsNullOrWhiteSpace(_o.HmacSecret)
            || !System.Text.RegularExpressions.Regex.IsMatch(receivedHmac ?? "", "^[0-9a-fA-F]{128}$"))
            return false;
        try
        {
            string[] fields =
            {
                Raw(obj, "amount_cents"), Raw(obj, "created_at"), Raw(obj, "currency"),
                Raw(obj, "error_occured"), Raw(obj, "has_parent_transaction"), Raw(obj, "id"),
                Raw(obj, "integration_id"), Raw(obj, "is_3d_secure"), Raw(obj, "is_auth"),
                Raw(obj, "is_capture"), Raw(obj, "is_refunded"), Raw(obj, "is_standalone_payment"),
                Raw(obj, "is_voided"), Raw(obj.GetProperty("order"), "id"), Raw(obj, "owner"),
                Raw(obj, "pending"), Raw(obj.GetProperty("source_data"), "pan"),
                Raw(obj.GetProperty("source_data"), "sub_type"),
                Raw(obj.GetProperty("source_data"), "type"), Raw(obj, "success")
            };
            using var h = new HMACSHA512(Encoding.UTF8.GetBytes(_o.HmacSecret));
            var computed = h.ComputeHash(Encoding.UTF8.GetBytes(string.Concat(fields)));
            return CryptographicOperations.FixedTimeEquals(computed, Convert.FromHexString(receivedHmac));
        }
        catch (KeyNotFoundException) { return false; }
        catch (InvalidOperationException) { return false; }
        catch (FormatException) { return false; }
    }

    // Emit each value exactly as it appears in JSON: booleans as true/false, numbers unquoted, strings raw.
    private static string Raw(JsonElement parent, string name)
    {
        var el = parent.GetProperty(name);
        return el.ValueKind switch
        {
            JsonValueKind.True => "true",
            JsonValueKind.False => "false",
            JsonValueKind.String => el.GetString() ?? "",
            JsonValueKind.Null or JsonValueKind.Undefined =>
                throw new InvalidOperationException("Missing HMAC field"),
            _ => el.GetRawText()
        };
    }
}
```

> **Boolean handling:** the `Raw` helper emits `true`/`false` (not `True`/`False`) and unquoted numbers, matching exactly what Paymob concatenated to produce the HMAC.

Keep refund/void/capture out of the basic checkout client. If required, implement the controlled application service described in `advanced-features.md` and `integration-safety.md`.

## Minimal-API endpoints (`Program.cs`)

```csharp
using System.Security.Claims;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;

app.MapPost("/api/checkout", async (CheckoutRequest dto, ClaimsPrincipal user,
    PaymobService paymob, ICheckoutStore checkoutStore) =>
{
    if (string.IsNullOrWhiteSpace(dto.CheckoutSessionId) || dto.CheckoutSessionId.Length > 200)
        return Results.BadRequest(new { error = "Invalid checkout session" });
    var attempt = await checkoutStore.PrepareAttemptAsync(dto.CheckoutSessionId,
        user.FindFirstValue(ClaimTypes.NameIdentifier)!);
    var (intentionId, clientSecret) = await paymob.CreateIntentionAsync(
        amountCents: attempt.AmountCents,
        currency: attempt.Currency,
        paymentMethods: attempt.PaymentMethods,
        specialReference: attempt.Reference,
        billingCountry: attempt.BillingCountry,
        c: attempt.Customer);
    await checkoutStore.AttachPaymobIntentionAsync(attempt.Id, intentionId);
    return Results.Ok(new {
        checkoutUrl = paymob.CheckoutUrl(clientSecret),
        checkoutAttemptToken = attempt.StatusToken
    });
}).RequireAuthorization();

app.MapPost("/api/paymob/webhook", async (HttpRequest req, PaymobService paymob, IPaymobPaymentEventStore paymentStore) =>
{
    if (!req.HasJsonContentType())
        return Results.Json(new { error = "JSON required" }, statusCode: 415);
    if (req.ContentLength > 65536)
        return Results.Json(new { error = "Payload too large" }, statusCode: 413);
    JsonDocument doc;
    try { doc = await JsonDocument.ParseAsync(req.Body); }
    catch (JsonException) { return Results.BadRequest(new { error = "Invalid JSON" }); }
    using (doc)
    {
    if (doc.RootElement.ValueKind != JsonValueKind.Object)
        return Results.BadRequest(new { error = "Invalid payload" });
    if (!doc.RootElement.TryGetProperty("obj", out var obj))
        return Results.Json(new { error = "no obj" }, statusCode: 400);
    if (obj.ValueKind != JsonValueKind.Object)
        return Results.BadRequest(new { error = "Invalid obj" });

    if (!req.Query.TryGetValue("hmac", out var receivedValues) || receivedValues.Count != 1)
        return Results.BadRequest(new { error = "One HMAC value required" });
    var received = receivedValues[0]!;
    if (!paymob.VerifyTransactionPostHmac(obj, received))
        return Results.Json(new { error = "Invalid HMAC" }, statusCode: 401);

    await paymentStore.RecordVerifiedEventAsync(
        providerEventId: obj.GetProperty("id").ToString(),
        paymobOrderId: obj.GetProperty("order").GetProperty("id").ToString(),
        merchantOrderId: obj.GetProperty("order").GetProperty("merchant_order_id").ToString(),
        amountCents: obj.GetProperty("amount_cents").GetInt64(),
        currency: obj.GetProperty("currency").GetString()!,
        integrationId: obj.GetProperty("integration_id").GetInt64(),
        owner: obj.GetProperty("owner").ToString(),
        classification: PaymobTransactionState.Classify(obj));
    return Results.Ok(new { received = true });
    }
}).WithMetadata(new RequestSizeLimitAttribute(65536));

record CheckoutRequest(string CheckoutSessionId);
```

The adapters and `PaymobTransactionState.Classify` are required application boundaries. Follow `integration-safety.md`: bind the verified event to the stored attempt, commit a binding mismatch as a quarantined no-op, insert a UNIQUE provider event keyed by `obj.id`, apply the ordered lifecycle classifier and compare-and-set, and insert a UNIQUE fulfillment outbox row only for a completed sale/capture. Throw only when the atomic persistence transaction fails. Return status through an authenticated, ownership-checked endpoint using `StatusToken`.

Register in DI: `builder.Services.AddSingleton(paymobOptions); builder.Services.AddHttpClient<PaymobService>(); builder.Services.AddScoped<ICheckoutStore, CheckoutStore>(); builder.Services.AddScoped<IPaymobPaymentEventStore, PaymobPaymentEventStore>();`

## Gotchas

- Header scheme is `Token` (not `Bearer`). Derive amount/items/currency/Integration IDs server-side. `phone_number` is required.
- Concatenate booleans as lowercase `true`/`false` (the `Raw` helper does this).
- Use `CryptographicOperations.FixedTimeEquals` (timing-safe). Verify HMAC before trusting `success`; never trust redirect params. `client_secret` is single-use.
- Validate the exact Paymob origin before attaching the Secret Key, and emit redacted structured logs only.
