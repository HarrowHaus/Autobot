import { Hono } from "hono";
import { convert } from "./engine.js";
import type { AccountingTarget, Env, Processor } from "./types.js";
import { UnrecognizedFormatError } from "./types.js";
import { consumeFreeTrial } from "./lib/rate-limit.js";
import { debitOneCredit, getOrCreateAccountByEmail, creditAccount, getCreditBalance } from "./lib/accounts.js";
import { findAccountIdByApiKey, issueApiKey } from "./lib/apikeys.js";
import { logConversion, logFailedConversion, logLandingPageQuery } from "./lib/signals.js";
import { createCreditPackCheckoutSession, CREDIT_PACKS, getStripeClient, type PackKey } from "./lib/billing.js";
import { newId } from "./lib/ids.js";
import { runGrowthLoopDetection } from "./growth-loop.js";

const PROCESSORS: Processor[] = ["stripe", "paypal", "square"];
const TARGETS: AccountingTarget[] = ["qbo", "xero"];

const app = new Hono<{ Bindings: Env }>();

function isProcessor(v: string): v is Processor {
  return (PROCESSORS as string[]).includes(v);
}
function isTarget(v: string): v is AccountingTarget {
  return (TARGETS as string[]).includes(v);
}

/**
 * Shared conversion handler for both the free-trial browser flow and the
 * credit-metered API flow. `spendCredit` decides how the caller pays.
 */
async function handleConversion(
  env: Env,
  csvText: string,
  processorRaw: string,
  targetRaw: string,
  accountId: string | null
): Promise<Response> {
  if (!isProcessor(processorRaw) || !isTarget(targetRaw)) {
    return Response.json({ error: "Unknown processor or target" }, { status: 400 });
  }

  try {
    const result = convert(csvText, processorRaw, targetRaw);
    await logConversion(env.DB, accountId, processorRaw, targetRaw, "ok", result.summary.transactionCount, null);
    return Response.json({ ...result, ok: true });
  } catch (err) {
    if (err instanceof UnrecognizedFormatError) {
      await logFailedConversion(env.DB, processorRaw, targetRaw, "unrecognized_format", err.header);
      await logConversion(env.DB, accountId, processorRaw, targetRaw, "error", null, "unrecognized_format");
      return Response.json(
        {
          ok: false,
          error: "unrecognized_format",
          message: err.message,
          hint: "We didn't recognize this file's columns. If you think this should work, tell us what platform it's from and we'll add support.",
        },
        { status: 422 }
      );
    }
    await logConversion(env.DB, accountId, processorRaw, targetRaw, "error", null, "internal_error");
    return Response.json({ ok: false, error: "internal_error", message: String(err) }, { status: 500 });
  }
}

// --- Browser upload flow: free trial, then pay-per-conversion credits ---
app.post("/convert", async (c) => {
  const form = await c.req.parseBody();
  const file = form["file"];
  const processor = String(form["processor"] ?? "");
  const target = String(form["target"] ?? "");
  const email = String(form["email"] ?? "").trim().toLowerCase();

  if (!(file instanceof File)) {
    return c.json({ ok: false, error: "missing_file" }, 400);
  }
  const csvText = await file.text();
  const ip = c.req.header("cf-connecting-ip") ?? "unknown";

  const gotFreeTrial = await consumeFreeTrial(c.env.CACHE, ip, email);
  let accountId: string | null = null;

  if (!gotFreeTrial) {
    if (!email) {
      return c.json({ ok: false, error: "email_required_after_trial" }, 402);
    }
    accountId = await getOrCreateAccountByEmail(c.env.DB, email);
    const spent = await debitOneCredit(c.env.DB, accountId);
    if (!spent) {
      return c.json(
        { ok: false, error: "no_credits", message: "Free trial used and no credits remaining. Buy a credit pack to continue.", buyUrl: "/billing/checkout" },
        402
      );
    }
  }

  return handleConversion(c.env, csvText, processor, target, accountId);
});

// --- API flow: API key auth, always metered ---
app.post("/v1/convert", async (c) => {
  const authHeader = c.req.header("authorization") ?? "";
  const key = authHeader.replace(/^Bearer\s+/i, "").trim();
  if (!key) return c.json({ ok: false, error: "missing_api_key" }, 401);

  const accountId = await findAccountIdByApiKey(c.env, key);
  if (!accountId) return c.json({ ok: false, error: "invalid_api_key" }, 401);

  const spent = await debitOneCredit(c.env.DB, accountId);
  if (!spent) {
    return c.json({ ok: false, error: "no_credits", buyUrl: "/billing/checkout?pack=api_100" }, 402);
  }

  const contentType = c.req.header("content-type") ?? "";
  let csvText: string;
  let processor: string;
  let target: string;

  if (contentType.includes("multipart/form-data")) {
    const form = await c.req.parseBody();
    const file = form["file"];
    if (!(file instanceof File)) return c.json({ ok: false, error: "missing_file" }, 400);
    csvText = await file.text();
    processor = String(form["processor"] ?? "");
    target = String(form["target"] ?? "");
  } else {
    const body = await c.req.json<{ csv: string; processor: string; target: string }>();
    csvText = body.csv;
    processor = body.processor;
    target = body.target;
  }

  return handleConversion(c.env, csvText, processor, target, accountId);
});

// --- Billing ---
app.post("/billing/checkout", async (c) => {
  const stripe = getStripeClient(c.env);
  if (!stripe) {
    return c.json({ ok: false, error: "billing_not_configured" }, 501);
  }

  const body = await c.req.json<{ pack: string; email: string }>().catch(() => null);
  const pack = body?.pack;
  const email = body?.email?.trim().toLowerCase();
  if (!pack || !(pack in CREDIT_PACKS) || !email) {
    return c.json({ ok: false, error: "invalid_request" }, 400);
  }

  const origin = new URL(c.req.url).origin;
  const session = await createCreditPackCheckoutSession(
    stripe,
    pack as PackKey,
    email,
    `${origin}/billing/success?session_id={CHECKOUT_SESSION_ID}`,
    `${origin}/#cancelled`
  );

  return c.json({ ok: true, url: session.url });
});

app.get("/billing/success", async (c) => {
  const sessionId = c.req.query("session_id");
  if (!sessionId) return c.json({ ok: false, error: "missing_session_id" }, 400);

  const row = await c.env.DB.prepare(
    `SELECT status, account_id, credits_granted FROM checkout_sessions WHERE stripe_session_id = ?`
  )
    .bind(sessionId)
    .first<{ status: string; account_id: string; credits_granted: number }>();

  if (!row) {
    // Webhook may not have landed yet — client should poll briefly.
    return c.json({ ok: true, status: "processing" });
  }

  const balance = await getCreditBalance(c.env.DB, row.account_id);
  return c.json({ ok: true, status: "fulfilled", creditBalance: balance });
});

app.post("/webhooks/stripe", async (c) => {
  const stripe = getStripeClient(c.env);
  if (!stripe || !c.env.STRIPE_WEBHOOK_SECRET) {
    return c.json({ ok: false, error: "billing_not_configured" }, 501);
  }

  const signature = c.req.header("stripe-signature");
  const rawBody = await c.req.text();
  if (!signature) return c.json({ ok: false, error: "missing_signature" }, 400);

  let event;
  try {
    event = await stripe.webhooks.constructEventAsync(rawBody, signature, c.env.STRIPE_WEBHOOK_SECRET);
  } catch (err) {
    return c.json({ ok: false, error: "invalid_signature" }, 400);
  }

  if (event.type === "checkout.session.completed") {
    const session = event.data.object;
    const email = (session.metadata?.email ?? session.customer_email ?? "").trim().toLowerCase();
    const credits = Number(session.metadata?.credits ?? 0);
    const pack = session.metadata?.pack ?? "unknown";

    if (email && credits > 0) {
      // INSERT OR IGNORE on the UNIQUE stripe_session_id makes this idempotent
      // under Stripe's at-least-once webhook delivery.
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

  return c.json({ ok: true });
});

// --- Growth-loop signal capture from the "didn't find your platform?" box ---
app.post("/feedback/missing-platform", async (c) => {
  const body = await c.req.json<{ query: string }>().catch(() => null);
  if (!body?.query) return c.json({ ok: false }, 400);
  await logLandingPageQuery(c.env.DB, body.query);
  return c.json({ ok: true });
});

app.get("/healthz", (c) => c.json({ ok: true, env: c.env.ENVIRONMENT }));

export default {
  fetch: app.fetch,
  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runGrowthLoopDetection(env);
  },
};
