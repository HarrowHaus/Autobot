import type { ValidationError } from "./money.js";

export type { ValidationError };

export function newCorrelationId(): string {
  return crypto.randomUUID();
}

/**
 * The only place internal error detail is allowed to be written. Never
 * include this detail in a response body — Cloudflare captures console
 * output separately from what's returned to the client.
 */
export function logServerError(correlationId: string, context: string, error: unknown): void {
  const detail = error instanceof Error ? (error.stack ?? error.message) : String(error);
  console.error(`[${correlationId}] ${context}: ${detail}`);
}

/** Structured validation/business errors — these messages are written to be shown to users, so they're returned as-is. */
export function errorResponse(status: number, correlationId: string, errors: ValidationError[]): Response {
  return Response.json({ ok: false, correlationId, errors }, { status });
}

/** An unexpected/internal failure — the client only ever sees a generic message plus the correlation ID to report. */
export function internalErrorResponse(status: number, correlationId: string): Response {
  return Response.json(
    {
      ok: false,
      correlationId,
      errors: [
        {
          code: "internal_error",
          field: "",
          message: `Something went wrong on our end. If this keeps happening, report it with correlation ID ${correlationId}.`,
        },
      ],
    },
    { status }
  );
}
