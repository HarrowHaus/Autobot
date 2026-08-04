import { newId } from "./ids.js";

/**
 * The only two things this alpha writes to D1. Neither stores file content,
 * and neither is tied to a user identity — there are no accounts.
 */

export async function logLandingPageQuery(db: D1Database, queryText: string): Promise<void> {
  await db
    .prepare(`INSERT INTO landing_page_queries (id, query_text) VALUES (?, ?)`)
    .bind(newId("lpq"), queryText.slice(0, 500))
    .run();
}

export async function logConversion(
  db: D1Database,
  processor: string,
  target: string,
  status: "ok" | "error",
  rowCount: number | null,
  errorCode: string | null
): Promise<void> {
  await db
    .prepare(
      `INSERT INTO conversions (id, processor, target, status, row_count, error_code) VALUES (?, ?, ?, ?, ?, ?)`
    )
    .bind(newId("conv"), processor, target, status, rowCount, errorCode)
    .run();
}
