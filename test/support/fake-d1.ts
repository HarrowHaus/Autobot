/**
 * Minimal in-memory stand-in for D1Database, covering exactly the query
 * shapes used by src/lib/accounts.ts, src/lib/apikeys.ts, src/lib/signals.ts,
 * and the inline queries in src/index.ts. This is NOT a general SQL engine —
 * it pattern-matches the fixed, known set of prepared statements this app
 * issues and mutates plain in-memory arrays. Wiring a real local D1 (via
 * @cloudflare/vitest-pool-workers) was judged not worth the added
 * infrastructure risk for this alpha's test suite; this fake exercises the
 * exact same call sequence (prepare/bind/first/run/batch, including
 * `meta.changes` gating) that the real D1 binding would, so it catches the
 * same class of bugs (e.g. double-crediting, lost no-op checks) that matter
 * here. See the final report for this explicitly documented scope decision.
 */

interface Account {
  id: string;
  email: string;
  stripe_customer_id: string | null;
  credit_balance: number;
}

interface ApiKey {
  id: string;
  account_id: string;
  key_hash: string;
  key_prefix: string;
  revoked_at: string | null;
  last_used_at: string | null;
}

interface CheckoutSession {
  id: string;
  stripe_session_id: string;
  kind: string;
  credits_granted: number;
  account_id: string | null;
  status: string;
}

interface CreditLedgerEntry {
  id: string;
  account_id: string;
  delta: number;
  reason: string;
  stripe_session_id: string | null;
}

interface Conversion {
  id: string;
  account_id: string | null;
  processor: string;
  target: string;
  status: string;
  row_count: number | null;
  error_code: string | null;
}

interface LandingPageQuery {
  id: string;
  query_text: string;
}

export class FakeD1Store {
  accounts: Account[] = [];
  apiKeys: ApiKey[] = [];
  checkoutSessions: CheckoutSession[] = [];
  creditLedger: CreditLedgerEntry[] = [];
  conversions: Conversion[] = [];
  landingPageQueries: LandingPageQuery[] = [];
}

class FakeStatement {
  private args: unknown[] = [];
  constructor(
    private store: FakeD1Store,
    private sql: string
  ) {}

  bind(...args: unknown[]): FakeStatement {
    const next = new FakeStatement(this.store, this.sql);
    next.args = args;
    return next;
  }

  async first<T = unknown>(): Promise<T | null> {
    return (dispatch(this.store, this.sql, this.args).first as T | null) ?? null;
  }

  async run(): Promise<{ meta: { changes: number } }> {
    const result = dispatch(this.store, this.sql, this.args);
    return { meta: { changes: result.changes } };
  }
}

export class FakeD1 {
  constructor(private store: FakeD1Store) {}

  prepare(sql: string): FakeStatement {
    return new FakeStatement(this.store, sql);
  }

  async batch(statements: FakeStatement[]): Promise<Array<{ meta: { changes: number } }>> {
    const results = [];
    for (const stmt of statements) {
      results.push(await stmt.run());
    }
    return results;
  }
}

function dispatch(store: FakeD1Store, sql: string, args: unknown[]): { first: unknown; changes: number } {
  const s = sql.replace(/\s+/g, " ").trim();

  if (s.startsWith("SELECT id FROM accounts WHERE email")) {
    const [email] = args as [string];
    const row = store.accounts.find((a) => a.email === email);
    return { first: row ? { id: row.id } : null, changes: 0 };
  }

  if (s.startsWith("INSERT INTO accounts")) {
    const [id, email] = args as [string, string];
    store.accounts.push({ id, email, stripe_customer_id: null, credit_balance: 0 });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("UPDATE accounts SET credit_balance = credit_balance - 1")) {
    const [id] = args as [string];
    const account = store.accounts.find((a) => a.id === id && a.credit_balance >= 1);
    if (!account) return { first: null, changes: 0 };
    account.credit_balance -= 1;
    return { first: null, changes: 1 };
  }

  if (s.startsWith("UPDATE accounts SET credit_balance = credit_balance + ?")) {
    const [delta, id] = args as [number, string];
    const account = store.accounts.find((a) => a.id === id);
    if (!account) return { first: null, changes: 0 };
    account.credit_balance += delta;
    return { first: null, changes: 1 };
  }

  if (s.startsWith("SELECT credit_balance FROM accounts WHERE id")) {
    const [id] = args as [string];
    const account = store.accounts.find((a) => a.id === id);
    return { first: account ? { credit_balance: account.credit_balance } : null, changes: 0 };
  }

  if (s.startsWith("INSERT INTO credit_ledger")) {
    const [id, account_id, delta, reason, stripe_session_id] = args as [string, string, number, string, string | null];
    store.creditLedger.push({ id, account_id, delta, reason, stripe_session_id });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("INSERT INTO api_keys")) {
    const [id, account_id, key_hash, key_prefix] = args as [string, string, string, string];
    store.apiKeys.push({ id, account_id, key_hash, key_prefix, revoked_at: null, last_used_at: null });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("SELECT account_id, id FROM api_keys WHERE key_hash")) {
    const [key_hash] = args as [string];
    const row = store.apiKeys.find((k) => k.key_hash === key_hash && k.revoked_at === null);
    return { first: row ? { account_id: row.account_id, id: row.id } : null, changes: 0 };
  }

  if (s.startsWith("UPDATE api_keys SET last_used_at")) {
    const [id] = args as [string];
    const row = store.apiKeys.find((k) => k.id === id);
    if (row) row.last_used_at = "now";
    return { first: null, changes: row ? 1 : 0 };
  }

  if (s.startsWith("SELECT id FROM api_keys WHERE account_id")) {
    const [account_id] = args as [string];
    const row = store.apiKeys.find((k) => k.account_id === account_id && k.revoked_at === null);
    return { first: row ? { id: row.id } : null, changes: 0 };
  }

  if (s.startsWith("SELECT status, account_id, credits_granted FROM checkout_sessions")) {
    const [stripe_session_id] = args as [string];
    const row = store.checkoutSessions.find((c) => c.stripe_session_id === stripe_session_id);
    return {
      first: row ? { status: row.status, account_id: row.account_id, credits_granted: row.credits_granted } : null,
      changes: 0,
    };
  }

  if (s.startsWith("INSERT OR IGNORE INTO checkout_sessions")) {
    const [id, stripe_session_id, kind, credits_granted] = args as [string, string, string, number];
    if (store.checkoutSessions.some((c) => c.stripe_session_id === stripe_session_id)) {
      return { first: null, changes: 0 };
    }
    store.checkoutSessions.push({ id, stripe_session_id, kind, credits_granted, account_id: null, status: "fulfilled" });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("UPDATE checkout_sessions SET account_id")) {
    const [account_id, stripe_session_id] = args as [string, string];
    const row = store.checkoutSessions.find((c) => c.stripe_session_id === stripe_session_id);
    if (row) row.account_id = account_id;
    return { first: null, changes: row ? 1 : 0 };
  }

  if (s.startsWith("INSERT INTO conversions")) {
    const [id, account_id, processor, target, status, row_count, error_code] = args as [
      string,
      string | null,
      string,
      string,
      string,
      number | null,
      string | null,
    ];
    store.conversions.push({ id, account_id, processor, target, status, row_count, error_code });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("INSERT INTO landing_page_queries")) {
    const [id, query_text] = args as [string, string];
    store.landingPageQueries.push({ id, query_text });
    return { first: null, changes: 1 };
  }

  throw new Error(`FakeD1: unrecognized query — add a case for it: ${s}`);
}

export function makeFakeD1(store: FakeD1Store = new FakeD1Store()): { db: FakeD1; store: FakeD1Store } {
  return { db: new FakeD1(store), store };
}
