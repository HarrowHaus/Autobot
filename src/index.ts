import { Hono } from "hono";
import { convert, isSupportedProcessor } from "./engine.js";
import { isBillingEnabled, type Env } from "./types.js";
import { checkRateLimit } from "./lib/rate-limit.js";
import { logConversion, logLandingPageQuery } from "./lib/signals.js";
import { newCorrelationId, logServerError, errorResponse, internalErrorResponse } from "./lib/errors.js";

const app = new Hono<{ Bindings: Env }>();

/**
 * This app is a non-production alpha. It validates one specific Stripe
 * export and produces a reconciliation report. It does not claim to produce
 * accounting-ready output.
 *
 * There is deliberately NO account, email, credit, API-key, checkout, or
 * webhook system here. Those were removed outright rather than left behind
 * a disabled flag: unreachable payment code is still code that can be
 * reached by a future mistake, and none of it had been reviewed or tested
 * against real money. If billing is ever wanted, it should be rebuilt
 * deliberately, not re-enabled.
 *
 * Access control is therefore rate limiting only.
 */
const MAX_BODY_BYTES = 10 * 1024 * 1024; // 10 MB
const MAX_FEEDBACK_QUERY_CHARS = 200;

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
    return errorResponse(429, newCorrelationId(), [
      { code: "rate_limited", field: "", message: "Too many requests. Please wait a moment and try again." },
    ]);
  }
  return null;
}

/**
 * Usage metadata logging is strictly best-effort. A D1 outage must never
 * fail a request or suppress a report the user has already successfully
 * earned — the report is the product; the log line is bookkeeping for us.
 */
async function logConversionBestEffort(
  correlationId: string,
  env: Env,
  processor: string,
  status: "ok" | "error",
  rowCount: number | null,
  errorCode: string | null
): Promise<void> {
  try {
    await logConversion(env.DB, processor, "reconciliation_report", status, rowCount, errorCode);
  } catch (err) {
    logServerError(correlationId, "logConversion (non-fatal)", err);
  }
}

app.post("/convert", async (c) => {
  const correlationId = newCorrelationId();
  const limited = await rateLimitOrReject(c, "convert", 10, 60);
  if (limited) return limited;

  try {
    if (contentLengthExceedsLimit(c.req.header("content-length"), MAX_BODY_BYTES)) {
      return errorResponse(413, correlationId, [
        { code: "file_too_large", field: "file", message: "File exceeds the 10 MB limit." },
      ]);
    }

    const form = await c.req.parseBody();
    const file = form["file"];
    const processorRaw = typeof form["processor"] === "string" ? form["processor"] : "stripe";

    if (!(file instanceof File)) {
      return errorResponse(400, correlationId, [{ code: "missing_file", field: "file", message: "No file was uploaded." }]);
    }
    if (file.size > MAX_BODY_BYTES) {
      return errorResponse(413, correlationId, [
        { code: "file_too_large", field: "file", message: "File exceeds the 10 MB limit." },
      ]);
    }
    if (!isSupportedProcessor(processorRaw)) {
      return errorResponse(400, correlationId, [
        { code: "unsupported_processor", field: "processor", message: `Processor "${processorRaw}" is not supported in this alpha.` },
      ]);
    }

    const csvText = await file.text();
    const result = await convert(csvText, processorRaw);

    if (!result.validation.ok) {
      await logConversionBestEffort(
        correlationId,
        c.env,
        processorRaw,
        "error",
        null,
        result.validation.blockingErrors[0]?.code ?? "validation_failed"
      );
      return errorResponse(422, correlationId, result.validation.blockingErrors);
    }

    await logConversionBestEffort(
      correlationId,
      c.env,
      processorRaw,
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

app.post("/feedback/missing-platform", async (c) => {
  const correlationId = newCorrelationId();
  const limited = await rateLimitOrReject(c, "feedback", 5, 60);
  if (limited) return limited;

  try {
    if (contentLengthExceedsLimit(c.req.header("content-length"), 64 * 1024)) {
      return errorResponse(413, correlationId, [{ code: "body_too_large", field: "", message: "Request body is too large." }]);
    }

    const body = await c.req.json<unknown>().catch(() => null);
    const query = body && typeof body === "object" && "query" in body ? (body as { query: unknown }).query : undefined;

    if (typeof query !== "string" || query.trim() === "") {
      return errorResponse(400, correlationId, [
        { code: "invalid_query", field: "query", message: "Expected a non-empty text value." },
      ]);
    }
    if (query.length > MAX_FEEDBACK_QUERY_CHARS) {
      return errorResponse(400, correlationId, [
        { code: "query_too_long", field: "query", message: `Keep it under ${MAX_FEEDBACK_QUERY_CHARS} characters.` },
      ]);
    }

    await logLandingPageQuery(c.env.DB, query.trim());
    return Response.json({ ok: true, correlationId });
  } catch (err) {
    logServerError(correlationId, "POST /feedback/missing-platform", err);
    return internalErrorResponse(500, correlationId);
  }
});

app.get("/healthz", (c) =>
  c.json({ ok: true, env: c.env.ENVIRONMENT, billingEnabled: isBillingEnabled(c.env) })
);

export default {
  fetch: app.fetch,
};
