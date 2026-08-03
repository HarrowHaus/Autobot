import { hashHeaderSignature } from "./csv.js";
import { newId } from "./ids.js";

/** Growth-loop input. Only a hashed header signature is stored — never row content. */
export async function logFailedConversion(
  db: D1Database,
  processorGuess: string | null,
  target: string | null,
  reasonCode: string,
  header: string[]
): Promise<void> {
  const headerHash = header.length > 0 ? await hashHeaderSignature(header) : null;
  await db
    .prepare(
      `INSERT INTO failed_conversion_signals (id, processor_guess, target, reason_code, header_signature_hash) VALUES (?, ?, ?, ?, ?)`
    )
    .bind(newId("fcs"), processorGuess, target, reasonCode, headerHash)
    .run();
}

export async function logLandingPageQuery(db: D1Database, queryText: string): Promise<void> {
  await db
    .prepare(`INSERT INTO landing_page_queries (id, query_text) VALUES (?, ?)`)
    .bind(newId("lpq"), queryText.slice(0, 500))
    .run();
}

export async function logConversion(
  db: D1Database,
  accountId: string | null,
  processor: string,
  target: string,
  status: "ok" | "error",
  rowCount: number | null,
  errorCode: string | null
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO conversions (id, account_id, processor, target, status, row_count, error_code) VALUES (?, ?, ?, ?, ?, ?, ?)`
    )
    .bind(newId("conv"), accountId, processor, target, status, rowCount, errorCode)
    .run();
}
