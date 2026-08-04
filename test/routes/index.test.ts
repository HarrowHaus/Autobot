import { describe, expect, it } from "vitest";
import worker from "../../src/index.js";
import type { Env } from "../../src/types.js";
import { FakeD1, FakeD1Store } from "../support/fake-d1.js";
import { FakeKV } from "../support/fake-kv.js";
import { buildStripeItemizedCsv, chargeRow } from "../support/stripe-fixture.js";

function makeEnv(overrides: Partial<Env> = {}): { env: Env; store: FakeD1Store; kv: FakeKV } {
  const store = new FakeD1Store();
  const kv = new FakeKV();
  const env = {
    DB: new FakeD1(store) as unknown as Env["DB"],
    CACHE: kv as unknown as Env["CACHE"],
    ASSETS: {} as unknown as Env["ASSETS"],
    ENVIRONMENT: "test",
    ...overrides,
  } as Env;
  return { env, store, kv };
}

function fileRequest(path: string, csv: string, extra: Record<string, string> = {}, ip = "1.1.1.1"): Request {
  const form = new FormData();
  form.set("file", new File([csv], "export.csv", { type: "text/csv" }));
  form.set("processor", "stripe");
  for (const [k, v] of Object.entries(extra)) form.set(k, v);
  return new Request(`http://localhost${path}`, {
    method: "POST",
    body: form,
    headers: { "cf-connecting-ip": ip },
  });
}

async function fetchApp(req: Request, env: Env): Promise<Response> {
  return worker.fetch(req, env, {} as ExecutionContext);
}

describe("GET /healthz", () => {
  it("reports ok and asserts billing is not enabled", async () => {
    const { env } = makeEnv();
    const res = await fetchApp(new Request("http://localhost/healthz"), env);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body).toMatchObject({ ok: true, billingEnabled: false });
  });
});

describe("removed surfaces — the billing/account system is gone, not gated", () => {
  it.each([
    ["POST", "/billing/checkout"],
    ["GET", "/billing/success"],
    ["POST", "/webhooks/stripe"],
    ["POST", "/v1/convert"],
  ])("%s %s does not exist", async (method, path) => {
    const { env } = makeEnv();
    const req = new Request(`http://localhost${path}`, {
      method,
      headers: { "cf-connecting-ip": "9.9.9.9" },
      ...(method === "POST" ? { body: "{}" } : {}),
    });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(404);
  });
});

describe("POST /convert — happy path", () => {
  it("validates a well-formed Stripe file and returns a report, with no identity required", async () => {
    const { env, store } = makeEnv();
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const res = await fetchApp(fileRequest("/convert", csv), env);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.ok).toBe(true);
    expect(body.report.payouts).toHaveLength(1);
    // Usage metadata is anonymous: no account linkage exists at all.
    expect(store.conversions).toHaveLength(1);
    expect(store.conversions[0]).not.toHaveProperty("account_id");
  });

  it("rejects a missing file", async () => {
    const { env } = makeEnv();
    const form = new FormData();
    form.set("processor", "stripe");
    const req = new Request("http://localhost/convert", { method: "POST", body: form, headers: { "cf-connecting-ip": "1.1.1.2" } });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(400);
    const body = (await res.json()) as any;
    expect(body.errors[0].code).toBe("missing_file");
  });

  it("rejects an unsupported processor", async () => {
    const { env } = makeEnv();
    const res = await fetchApp(fileRequest("/convert", "x", { processor: "paypal" }, "1.1.1.9"), env);
    expect(res.status).toBe(400);
    const body = (await res.json()) as any;
    expect(body.errors[0].code).toBe("unsupported_processor");
  });

  it("rejects a file over the size limit", async () => {
    const { env } = makeEnv();
    const form = new FormData();
    const big = new Uint8Array(10 * 1024 * 1024 + 1);
    form.set("file", new File([big], "big.csv", { type: "text/csv" }));
    form.set("processor", "stripe");
    const req = new Request("http://localhost/convert", { method: "POST", body: form, headers: { "cf-connecting-ip": "1.1.1.3" } });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(413);
  });

  it("returns a 422 with structured errors when validation fails", async () => {
    const { env } = makeEnv();
    const res = await fetchApp(fileRequest("/convert", "not,a,stripe,file\n1,2,3,4\n", {}, "1.1.1.4"), env);
    expect(res.status).toBe(422);
    const body = (await res.json()) as any;
    expect(body.ok).toBe(false);
    expect(body.correlationId).toBeTruthy();
    expect(body.errors.length).toBeGreaterThan(0);
  });
});

describe("POST /convert — D1 logging is best-effort", () => {
  it("still returns the report when the usage-metadata write fails", async () => {
    const { env } = makeEnv();
    // Simulate D1 being unavailable for writes.
    (env.DB as unknown as { prepare: () => unknown }).prepare = () => ({
      bind: () => ({
        run: async () => {
          throw new Error("D1_ERROR: database unavailable");
        },
        first: async () => null,
      }),
    });

    const csv = buildStripeItemizedCsv([chargeRow()]);
    const res = await fetchApp(fileRequest("/convert", csv, {}, "8.8.8.8"), env);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.ok).toBe(true);
    expect(body.report.payouts).toHaveLength(1);
  });
});

describe("POST /convert — rate limiting", () => {
  it("rejects the 11th request within a window from the same IP", async () => {
    const { env } = makeEnv();
    const ip = "5.5.5.5";
    let last!: Response;
    for (let i = 0; i < 11; i++) {
      last = await fetchApp(fileRequest("/convert", "bad,file\n1,2\n", {}, ip), env);
    }
    expect(last.status).toBe(429);
  });
});

describe("POST /feedback/missing-platform — input validation", () => {
  it("records a valid query", async () => {
    const { env, store } = makeEnv();
    const res = await fetchApp(
      new Request("http://localhost/feedback/missing-platform", {
        method: "POST",
        headers: { "content-type": "application/json", "cf-connecting-ip": "7.7.7.1" },
        body: JSON.stringify({ query: "Square" }),
      }),
      env
    );
    expect(res.status).toBe(200);
    expect(store.landingPageQueries).toHaveLength(1);
  });

  it.each([
    ["a non-string query", { query: 12345 }],
    ["an object query", { query: { nested: true } }],
    ["an array query", { query: ["a"] }],
    ["a missing query", {}],
    ["a blank query", { query: "   " }],
  ])("rejects %s", async (_label, body) => {
    const { env, store } = makeEnv();
    const res = await fetchApp(
      new Request("http://localhost/feedback/missing-platform", {
        method: "POST",
        headers: { "content-type": "application/json", "cf-connecting-ip": "7.7.7.2" },
        body: JSON.stringify(body),
      }),
      env
    );
    expect(res.status).toBe(400);
    expect(store.landingPageQueries).toHaveLength(0);
  });

  it("rejects an over-long query", async () => {
    const { env } = makeEnv();
    const res = await fetchApp(
      new Request("http://localhost/feedback/missing-platform", {
        method: "POST",
        headers: { "content-type": "application/json", "cf-connecting-ip": "7.7.7.3" },
        body: JSON.stringify({ query: "x".repeat(201) }),
      }),
      env
    );
    expect(res.status).toBe(400);
    const body = (await res.json()) as any;
    expect(body.errors[0].code).toBe("query_too_long");
  });

  it("rate-limits after 5 requests per window", async () => {
    const { env, store } = makeEnv();
    const ip = "7.7.7.7";
    let last!: Response;
    for (let i = 0; i < 6; i++) {
      last = await fetchApp(
        new Request("http://localhost/feedback/missing-platform", {
          method: "POST",
          headers: { "content-type": "application/json", "cf-connecting-ip": ip },
          body: JSON.stringify({ query: `square ${i}` }),
        }),
        env
      );
    }
    expect(last.status).toBe(429);
    expect(store.landingPageQueries).toHaveLength(5);
  });
});
