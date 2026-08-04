/// <reference types="@cloudflare/workers-types" />

export type Processor = "stripe";
export type AccountingTarget = "qbo";

export class UnrecognizedFormatError extends Error {
  header: string[];
  constructor(message: string, header: string[]) {
    super(message);
    this.name = "UnrecognizedFormatError";
    this.header = header;
  }
}

/**
 * PayoutSplit is a non-production alpha.
 *
 * There is no billing code in this Worker at all — the account, credit,
 * API-key, checkout, and webhook system was deleted rather than disabled.
 * BILLING_ENABLED is retained only as an explicit, externally-visible
 * assertion (surfaced on /healthz) that no payment path exists; there is
 * nothing it could switch on.
 *
 * ALLOW_QBO_EXPORT does gate real behavior: the QuickBooks journal builder
 * exists and is tested, but must not be offered until its output has been
 * imported into a real QuickBooks sandbox and verified.
 */
export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  ASSETS: Fetcher;
  ENVIRONMENT: string;
  BILLING_ENABLED?: string;
  ALLOW_QBO_EXPORT?: string;
}

/** Always false in this alpha: no payment path is implemented. */
export function isBillingEnabled(env: Env): boolean {
  return env.BILLING_ENABLED === "true";
}

export function isQboExportAllowed(env: Env): boolean {
  return env.ALLOW_QBO_EXPORT === "true";
}
