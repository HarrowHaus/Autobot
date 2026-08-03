/// <reference types="@cloudflare/workers-types" />

export type Processor = "stripe" | "paypal" | "square";
export type AccountingTarget = "qbo" | "xero";

export interface NormalizedTransaction {
  date: string; // YYYY-MM-DD
  type: "charge" | "refund" | "fee" | "adjustment" | "other";
  grossCents: number;
  feeCents: number;
  netCents: number;
  currency: string;
  /** Transactions sharing a payoutId become a single bank deposit line. */
  payoutId: string;
  description: string;
}

export interface ConversionResult {
  journalFile: { filename: string; content: string; mimeType: string };
  bankMatchFile: { filename: string; content: string; mimeType: string };
  summary: {
    payoutCount: number;
    transactionCount: number;
    totalGrossCents: number;
    totalFeeCents: number;
    totalNetCents: number;
  };
}

export class UnrecognizedFormatError extends Error {
  header: string[];
  constructor(message: string, header: string[]) {
    super(message);
    this.name = "UnrecognizedFormatError";
    this.header = header;
  }
}

export interface Env {
  DB: D1Database;
  CACHE: KVNamespace;
  ASSETS: Fetcher;
  ENVIRONMENT: string;
  STRIPE_SECRET_KEY?: string;
  STRIPE_WEBHOOK_SECRET?: string;
  GITHUB_TOKEN?: string;
}
