/**
 * Minimal in-memory stand-in for D1Database, covering exactly the two
 * INSERT statements this app issues (see src/lib/signals.ts — that is the
 * complete set of database writes). This is NOT a general SQL engine; it
 * pattern-matches those known statements and appends to plain arrays.
 *
 * It does not replace testing against a real local D1 binding, which is
 * still on the manual-validation list.
 */

interface Conversion {
  id: string;
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
    return { meta: { changes: dispatch(this.store, this.sql, this.args).changes } };
  }
}

export class FakeD1 {
  constructor(private store: FakeD1Store) {}

  prepare(sql: string): FakeStatement {
    return new FakeStatement(this.store, sql);
  }
}

function dispatch(store: FakeD1Store, sql: string, args: unknown[]): { first: unknown; changes: number } {
  const s = sql.replace(/\s+/g, " ").trim();

  if (s.startsWith("INSERT INTO conversions")) {
    const [id, processor, target, status, row_count, error_code] = args as [
      string,
      string,
      string,
      string,
      number | null,
      string | null,
    ];
    store.conversions.push({ id, processor, target, status, row_count, error_code });
    return { first: null, changes: 1 };
  }

  if (s.startsWith("INSERT INTO landing_page_queries")) {
    const [id, query_text] = args as [string, string];
    store.landingPageQueries.push({ id, query_text });
    return { first: null, changes: 1 };
  }

  throw new Error(`FakeD1: unrecognized query — add a case for it: ${s}`);
}
