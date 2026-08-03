import { Hono } from "hono";
import { convert, isSupportedProcessor } from "./engine.js";
import { isBillingEnabled, type Env } from "./types.js";
import { checkRateLimit, hasUsedFreeTrial, markFreeTrialUsed } from "./lib/rate-limit.js";
import { debitOneCredit, getOrCreateAccountByEmail, creditAccount, getCreditBalance } from "./lib/accounts.js";
import { findAccountIdByApiKey, issueApiKey } from "./lib/apikeys.js";
import { logConversion, logLandingPageQuery } from "./lib/signals.js";
import { createCreditPackCheckoutSession, CREDIT_PACKS, getStripeClient, type PackKey } from "./lib/billing.js";
import { newId } from "./lib/ids.js";
import { newCorrelationId, logServerError, errorResponse, internalErrorResponse } from "./lib/errors.js";

const app = new Hono<{ Bindings: Env }>();

// This app is a non-production alpha: it validates one specific Stripe
// export and produces a reconciliation report. It does not claim to produce
// accounting-ready output, and does not accept payment while
// BILLING_ENABLED is unset/false.
const MAX_BODY_BYTES = 10 * 1024 * 1024; // 10 MB

function clientIp(c: { req: { header: (name: string) => string | undefined } }): string {
  return c.req.header("cf-connecting-ip") ?? "unknown";
}

function contentLengthExceedsLimit(contentLength: string | undefined, max: number): boolean {
  if (!contentLength) return false;
  const n = Number(contentLength);
  return Number.isFinite(n) && n > max;
}

async function rateLimitOrReject(
  c: { env: Env; req: { header: (name: string) => string | undefined } },
  routeKey: string,
  limit: number,
  windowSeconds: number
): Promise<Response | null> {
  const result = await checkRateLimit(c.env.CACHE, routeKey, clientIp(c), limit, windowSeconds);
  if (!result.allowed) {
    const correlationId = newCorrelationId();
    return errorResponse(429, correlationId, [
      { code: "rate_limited", field: "", message: "Too many requests. Please wait a moment and try again." },
    ]);
  }
  return null;
}

// --- Browser upload flow: free trial (validated first), then credits ---
app.post("/convert", async (c) => {
  const correlationId = newCorrelationId();
  const limited = await rateLimitOrReject(c, "convert", 10, 60);
  if (limited) return limited;

  try {
    const contentLength = c.req.header("content-length");
    if (contentLengthExceedsLimit(contentLength, MAX_BODY_BYTES)) {
      return errorResponse(413, correlationId, [
        { code: "file_too_large", field: "file", message: "File exceeds the 10 MB limit." },
      ]);
    }

    const form = await c.req.parseBody();
    const file = form["file"];
    const processorRaw = String(form["processor"] ?? "stripe");
    const email = String(form["email"] ?? "").trim().toLowerCase();

    if (!(file instanceof File)) {
      return errorResponse(400, correlationId, [{ code: "missing_file", field: "file", message: "No file was uploaded." }]);
    }
    if (file.size > MAX_BODY_BYTES) {
      return errorResponse(413, correlationId, [
        { code: "file_too_large", field: "file", message: "File exceeds the 10 MB limit." },
      ]);
    }

    const ip = clientIp(c);
    const usedTrial = await hasUsedFreeTrial(c.env.CACHE, ip, email);
    let accountId: string | null = null;

    if (usedTrial) {
      if (!email) {
        return errorResponse(402, correlationId, [
          { code: "email_required_after_trial", field: "email", message: "Enter your email to continue after your free conversion." },
        ]);
      }
      accountId = await getOrCreateAccountByEmail(c.env.DB, email);
      const balance = await getCreditBalance(c.env.DB, accountId);
      if (balance < 1) {
        return errorResponse(402, correlationId, [
          {
            code: "no_credits",
            field: "",
            message: "Free trial used and no credits remaining. This is an early alpha; purchasing isn't enabled yet.",
          },
        ]);
      }
    }

    const csvText = await file.text();
    const result = await convert(csvText, processorRaw);

    if (!result.validation.ok) {
      await logConversion(c.env.DB, accountId, processorRaw, "reconciliation_report", "error", null, result.validation.blockingErrors[0]?.code ?? "validation_failed");
      return errorResponse(422, correlationId, result.validation.blockingErrors);
    }

    // Only now — after a fully successful validation — do we consume the
    // trial or a credit. An invalid file never costs the user anything.
    if (usedTrial) {
      const spent = await debitOneCredit(c.env.DB, accountId!);
      if (!spent) {
        // Rare race: balance changed between the check above and now.
        return errorResponse(402, correlationId, [
          { code: "no_credits", field: "", message: "No credits remaining." },
        ]);
      }
    } else {
      await markFreeTrialUsed(c.env.CACHE, ip, email);
    }

    await logConversion(
      c.env.DB,
      accountId,
      processorRaw,
      "reconciliation_report",
      "ok",
      result.validation.report!.includedRowCount,
      null
    );

    return Response.json({ ok: true, correlationId, report: result.validation.report });
  } catch (err) {
    logServerError(correlationId, "POST /convert", err);
    return internalErrorResponse(500, correlationId);
  }
});

// --- API flow: API key auth, always metered, validated before debit ---
app.post("/v1/convert", async (c) => {
  const correlationId = newCorrelationId();

  try {
    const authHeader = c.req.header("authorization") ?? "";
    const key = authHeader.replace(/^Bearer\s+/i, "").trim();
    if (!key) return errorResponse(401, correlationId, [{ code: "missing_api_key", field: "", message: "Missing API key." }]);

    const accountId = await findAccountIdByApiKey(c.env, key);
    if (!accountId) return errorResponse(401, correlationId, [{ code: "invalid_api_key", field: "", message: "Invalid API key." }]);

    const balance = await getCreditBalance(c.env.DB, accountId);
    if (balance < 1) {
      return errorResponse(402, correlationId, [{ code: "no_credits", field: "", message: "No credits remaining." }]);
    }

    const contentLength = c.req.header("content-length");
    if (contentLengthExceedsLimit(contentLength, MAX_BODY_BYTES)) {
      return errorResponse(413, correlationId, [{ code: "file_too_large", field: "file", message: "Body exceeds the 10 MB limit." }]);
    }

    const contentType = c.req.header("content-type") ?? "";
    let csvText: string;
    let processorRaw: string;

    if (contentType.includes("multipart/form-data")) {
      const form = await c.req.parseBody();
      const file = form["file"];
      if (!(file instanceof File)) return errorResponse(400, correlationId, [{ code: "missing_file", field: "file", message: "No file was uploaded." }]);
      if (file.size > MAX_BODY_BYTES) {
        return errorResponse(413, correlationId, [{ code: "file_too_large", field: "file", message: "File exceeds the 10 MB limit." }]);
      }
      csvText = await file.text();
      processorRaw = String(form["processor"] ?? "stripe");
    } else {
      const body = await c.req.json<{ csv: string; processor: string }>();
      csvText = body.csv ?? "";
      processorRaw = body.processor ?? "stripe";
      if (new TextEncoder().encode(csvText).length > MAX_BODY_BYTES) {
        return errorResponse(413, correlationId, [{ code: "file_too_large", field: "csv", message: "CSV exceeds the 10 MB limit." }]);
      }
    }

    if (!isSupportedProcessor(processorRaw)) {
      return errorResponse(400, correlationId, [
        { code: "unsupported_processor", field: "processor", message: `Processor "${processorRaw}" is not supported in this alpha.` },
      ]);
    }

    const result = await convert(csvText, processorRaw);

    if (!result.validation.ok) {
      await logConversion(c.env.DB, accountId, processorRaw, "reconciliation_report", "error", null, result.validation.blockingErrors[0]?.code ?? "validation_failed");
      return errorResponse(422, correlationId, result.validation.blockingErrors);
    }

    const spent = await debitOneCredit(c.env.DB, accountId);
    if (!spent) {
      return errorResponse(402, correlationId, [{ code: "no_credits", field: "", message: "No credits remaining." }]);
    }

    await logConversion(c.env.DB, accountId, processorRaw, "reconciliation_report", "ok", result.validation.report!.includedRowCount, null);

    return Response.json({ ok: true, correlationId, report: result.validation.report });
  } catch (err) {
    logServerError(correlationId, "POST /v1/convert", err);
    return internalErrorResponse(500, correlationId);
  }
});

// --- Billing: disabled by default in this alpha ---
app.post("/billing/checkout", async (c) => {
  const correlationId = newCorrelationId();
  const limited = await rateLimitOrReject(c, "billing-checkout", 10, 60);
  if (limited) return limited;

  if (!isBillingEnabled(c.env)) {
    return errorResponse(503, correlationId, [
      { code: "billing_disabled", field: "", message: "Billing is disabled in this alpha. No payment is currently accepted." },
    ]);
  }

  try {
    const stripe = getStripeClient(c.env);
    if (!stripe) {
      return errorResponse(503, correlationId, [{ code: "billing_not_configured", field: "", message: "Billing is not configured." }]);
    }

    const body = await c.req.json<{ pack: string; email: string }>().catch(() => null);
    const pack = body?.pack;
    const email = body?.email?.trim().toLowerCase();
    if (!pack || !(pack in CREDIT_PACKS) || !email) {
      return errorResponse(400, correlationId, [{ code: "invalid_request", field: "", message: "Invalid checkout request." }]);
    }

    const origin = new URL(c.req.url).origin;
    const session = await createCreditPackCheckoutSession(
      stripe,
      pack as PackKey,
      email,
      `${origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
      `${origin}/#cancelled`
    );

    return Response.json({ ok: true, correlationId, url: session.url });
  } catch (err) {
    logServerError(correlationId, "POST /billing/checkout", err);
    return internalErrorResponse(500, correlationId);
  }
});

app.get("/billing/success", async (c) => {
  const correlationId = newCorrelationId();
  const sessionId = c.req.query("session_id");
  if (!sessionId) return errorResponse(400, correlationId, [{ code: "missing_session_id", field: "", message: "Missing session_id." }]);

  try {
    const row = await c.env.DB.prepare(
      `SELECT status, account_id, credits_granted FROM checkout_sessions WHERE stripe_session_id = ?`
    )
      .bind(sessionId)
      .first<{ status: string; account_id: string; credits_granted: number }>();

    if (!row) {
      return Response.json({ ok: true, correlationId, status: "processing" });
    }

    const balance = await getCreditBalance(c.env.DB, row.account_id);
    return Response.json({ ok: true, correlationId, status: "fulfilled", creditBalance: balance });
  } catch (err) {
    logServerError(correlationId, "GET /billing/success", err);
    return internalErrorResponse(500, correlationId);
  }
});

app.post("/webhooks/stripe", async (c) => {
  const correlationId = newCorrelationId();

  if (!isBillingEnabled(c.env)) {
    return errorResponse(503, correlationId, [{ code: "billing_disabled", field: "", message: "Billing is disabled in this alpha." }]);
  }

  try {
    const stripe = getStripeClient(c.env);
    if (!stripe || !c.env.STRIPE_WEBHOOK_SECRET) {
      return errorResponse(503, correlationId, [{ code: "billing_not_configured", field: "", message: "Billing is not configured." }]);
    }

    const signature = c.req.header("stripe-signature");
    const rawBody = await c.req.text();
    if (!signature) return errorResponse(400, correlationId, [{ code: "missing_signature", field: "", message: "Missing signature." }]);

    let event;
    try {
      event = await stripe.webhooks.constructEventAsync(rawBody, signature, c.env.STRIPE_WEBHOOK_SECRET);
    } catch {
      return errorResponse(400, correlationId, [{ code: "invalid_signature", field: "", message: "Invalid signature." }]);
    }

    if (event.type === "checkout.session.completed") {
      const session = event.data.object;
      const email = (session.metadata?.email ?? session.customer_email ?? "").trim().toLowerCase();
      const credits = Number(session.metadata?.credits ?? 0);
      const pack = session.metadata?.pack ?? "unknown";

      if (email && credits > 0) {
        const inserted = await c.env.DB.prepare(
          `INSERT OR IGNORE INTO checkout_sessions (id, stripe_session_id, kind, credits_granted, status) VALUES (?, ?, ?, ?, 'fulfilled')`
        )
          .bind(newId("cs"), session.id, pack.startsWith("api_") ? "api_credit_pack" : "web_credit_pack", credits)
          .run();

        if ((inserted.meta.changes ?? 0) > 0) {
          const accountId = await getOrCreateAccountByEmail(c.env.DB, email);
          await creditAccount(c.env.DB, accountId, credits, "purchase", session.id);
          await c.env.DB.prepare(`UPDATE checkout_sessions SET account_id = ? WHERE stripe_session_id = ?`)
            .bind(accountId, session.id)
            .run();

          if (pack.startsWith("api_")) {
            const existingKey = await c.env.DB.prepare(`SELECT id FROM api_keys WHERE account_id = ? AND revoked_at IS NULL`)
              .bind(accountId)
              .first();
            if (!existingKey) await issueApiKey(c.env.DB, accountId);
          }
        }
      }
    }

    return Response.json({ ok: true, correlationId });
  } catch (err) {
    logServerError(correlationId, "POST /webhooks/stripe", err);
    return internalErrorResponse(500, correlationId);
  }
});

// --- Feedback / "didn't find your platform" ---
app.post("/feedback/missing-platform", async (c) => {
  const correlationId = newCorrelationId();
  const limited = await rateLimitOrReject(c, "feedback", 5, 60);
  if (limited) return limited;

  try {
    const body = await c.req.json<{ query: string }>().catch(() => null);
    if (!body?.query) return errorResponse(400, correlationId, [{ code: "missing_query", field: "query", message: "Missing query." }]);
    await logLandingPageQuery(c.env.DB, body.query);
    return Response.json({ ok: true, correlationId });
  } catch (err) {
    logServerError(correlationId, "POST /feedback/missing-platform", err);
    return internalErrorResponse(500, correlationId);
  }
});

app.get("/healthz", (c) => c.json({ ok: true, env: c.env.ENVIRONMENT, billingEnabled: isBillingEnabled(c.env) }));

export default {
  fetch: app.fetch,
};
