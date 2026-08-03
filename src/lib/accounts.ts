import { newId } from "./ids.js";

export async function getOrCreateAccountByEmail(db: D1Database, email: string): Promise<string> {
  const existing = await db
    .prepare(`SELECT id FROM accounts WHERE email = ?`)
    .bind(email)
    .first<{ id: string }>();
  if (existing) return existing.id;

  const id = newId("acct");
  await db.prepare(`INSERT INTO accounts (id, email) VALUES (?, ?)`).bind(id, email).run();
  return id;
}

/** Atomically debits 1 credit. Returns false if the account has no credits left. */
export async function debitOneCredit(db: D1Database, accountId: string): Promise<boolean> {
  const result = await db
    .prepare(`UPDATE accounts SET credit_balance = credit_balance - 1 WHERE id = ? AND credit_balance >= 1`)
    .bind(accountId)
    .run();
  return (result.meta.changes ?? 0) > 0;
}

export async function creditAccount(
  db: D1Database,
  accountId: string,
  delta: number,
  reason: string,
  stripeSessionId: string | null
): Promise<void> {
  await db.batch([
    db
      .prepare(`UPDATE accounts SET credit_balance = credit_balance + ? WHERE id = ?`)
      .bind(delta, accountId),
    db
      .prepare(
        `INSERT INTO credit_ledger (id, account_id, delta, reason, stripe_session_id) VALUES (?, ?, ?, ?, ?)`
      )
      .bind(newId("ledger"), accountId, delta, reason, stripeSessionId),
  ]);
}

export async function getCreditBalance(db: D1Database, accountId: string): Promise<number> {
  const row = await db
    .prepare(`SELECT credit_balance FROM accounts WHERE id = ?`)
    .bind(accountId)
    .first<{ credit_balance: number }>();
  return row?.credit_balance ?? 0;
}
