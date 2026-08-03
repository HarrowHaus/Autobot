import { newId } from "./ids.js";

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
