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
 * PayoutSplit is a non-production alpha. BILLING_ENABLED and
 * ALLOW_QBO_EXPORT default to "false" and gate the only two things in this
 * app that could cause real financial harm if wrong: charging real money,
 * and producing a file someone imports directly into their books.
 */
export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  ASSETS: Fetcher;
  ENVIRONMENT: string;
  BILLING_ENABLED?: string;
  ALLOW_QBO_EXPORT?: string;
  STRIPE_SECRET_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  GITHUB_TOKEN?: string;
}

export function isBillingEnabled(env: Env): boolean {
  return env.BILLING_ENABLED === "true";
}

export function isQboExportAllowed(env: Env): boolean {
  return env.ALLOW_QBO_EXPORT === "true";
}
