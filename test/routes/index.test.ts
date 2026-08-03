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
  it("reports ok and the current billing-enabled state", async () => {
    const { env } = makeEnv();
    const res = await fetchApp(new Request("http://localhost/healthz"), env);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body).toMatchObject({ ok: true, billingEnabled: false });
  });
});

describe("POST /convert — happy path", () => {
  it("validates a well-formed Stripe file on the free trial and returns a report", async () => {
    const { env, kv } = makeEnv();
    const csv = buildStripeItemizedCsv([chargeRow()]);
    const res = await fetchApp(fileRequest("/convert", csv), env);
    expect(res.status).toBe(200);
    const body = (await res.json()) as any;
    expect(body.ok).toBe(true);
    expect(body.report.payouts).toHaveLength(1);
    expect(kv.store.has("trial:1.1.1.1:anon")).toBe(true);
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
});

describe("POST /convert — no credit/trial loss on invalid input", () => {
  it("does not consume the free trial when the uploaded file fails validation", async () => {
    const { env, kv } = makeEnv();
    const ip = "2.2.2.2";
    const email = "trial@example.com";

    const badRes = await fetchApp(fileRequest("/convert", "not,a,valid,stripe,file\n1,2,3,4,5\n", { email }, ip), env);
    expect(badRes.status).toBe(422);
    expect(kv.store.has(`trial:${ip}:${email}`)).toBe(false);

    const goodCsv = buildStripeItemizedCsv([chargeRow()]);
    const goodRes = await fetchApp(fileRequest("/convert", goodCsv, { email }, ip), env);
    expect(goodRes.status).toBe(200);
    const body = (await goodRes.json()) as any;
    expect(body.ok).toBe(true);
    expect(kv.store.has(`trial:${ip}:${email}`)).toBe(true);
  });

  it("does not debit a credit when a paying account's upload fails validation", async () => {
    const { env, store, kv } = makeEnv();
    const ip = "3.3.3.3";
    const email = "paying@example.com";
    store.accounts.push({ id: "acct_1", email, stripe_customer_id: null, credit_balance: 3 });
    await kv.put(`trial:${ip}:${email}`, "1");

    const badRes = await fetchApp(fileRequest("/convert", "garbage\n1\n", { email }, ip), env);
    expect(badRes.status).toBe(422);
    expect(store.accounts.find((a) => a.id === "acct_1")!.credit_balance).toBe(3);

    const goodCsv = buildStripeItemizedCsv([chargeRow()]);
    const goodRes = await fetchApp(fileRequest("/convert", goodCsv, { email }, ip), env);
    expect(goodRes.status).toBe(200);
    expect(store.accounts.find((a) => a.id === "acct_1")!.credit_balance).toBe(2);
  });

  it("returns 402 with no credits remaining rather than allowing an over-limit conversion", async () => {
    const { env, store, kv } = makeEnv();
    const ip = "4.4.4.4";
    const email = "empty@example.com";
    store.accounts.push({ id: "acct_2", email, stripe_customer_id: null, credit_balance: 0 });
    await kv.put(`trial:${ip}:${email}`, "1");

    const csv = buildStripeItemizedCsv([chargeRow()]);
    const res = await fetchApp(fileRequest("/convert", csv, { email }, ip), env);
    expect(res.status).toBe(402);
    const body = (await res.json()) as any;
    expect(body.errors[0].code).toBe("no_credits");
  });
});

describe("POST /convert — rate limiting", () => {
  it("rejects the 11th request within a window from the same IP", async () => {
    const { env } = makeEnv();
    const ip = "5.5.5.5";
    let last!: Response;
    for (let i = 0; i < 11; i++) {
      last = await fetchApp(fileRequest("/convert", "bad,file\n1,2\n", { email: `u${i}@example.com` }, ip), env);
    }
    expect(last.status).toBe(429);
  });
});

describe("POST /billing/checkout — disabled by default", () => {
  it("returns 503 billing_disabled when BILLING_ENABLED is unset", async () => {
    const { env } = makeEnv();
    const req = new Request("http://localhost/billing/checkout", {
      method: "POST",
      headers: { "content-type": "application/json", "cf-connecting-ip": "6.6.6.6" },
      body: JSON.stringify({ pack: "web_1", email: "a@example.com" }),
    });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(503);
    const body = (await res.json()) as any;
    expect(body.errors[0].code).toBe("billing_disabled");
  });

  it("stays disabled even when explicitly set to a non-'true' value", async () => {
    const { env } = makeEnv({ BILLING_ENABLED: "1" });
    const req = new Request("http://localhost/billing/checkout", {
      method: "POST",
      headers: { "content-type": "application/json", "cf-connecting-ip": "6.6.6.7" },
      body: JSON.stringify({ pack: "web_1", email: "a@example.com" }),
    });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(503);
  });
});

describe("POST /webhooks/stripe — disabled by default", () => {
  it("returns 503 billing_disabled without attempting signature verification", async () => {
    const { env } = makeEnv();
    const req = new Request("http://localhost/webhooks/stripe", { method: "POST", body: "{}" });
    const res = await fetchApp(req, env);
    expect(res.status).toBe(503);
  });
});

describe("POST /feedback/missing-platform", () => {
  it("records the query and rate-limits after 5 requests per window", async () => {
    const { env, store } = makeEnv();
    const ip = "7.7.7.7";
    let last!: Response;
    for (let i = 0; i < 6; i++) {
      last = await fetchApp(
        new Request("http://localhost/feedback/missing-platform", {
          method: "POST",
          headers: { "content-type": "application/json", "cf-connecting-ip": ip },
          body: JSON.stringify({ query: `square to xero ${i}` }),
        }),
        env
      );
    }
    expect(last.status).toBe(429);
    expect(store.landingPageQueries.length).toBe(5);
  });
});
