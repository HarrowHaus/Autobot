import test from "node:test";
import assert from "node:assert/strict";
import {
  atomicUsdcToDollar,
  buildRouteConfig,
  tokenize,
  rankPeers,
} from "../cloudflare/merchant-worker.js";

test("official x402 route config is Base exact USDC-priced", () => {
  const routes = buildRouteConfig("https://example.workers.dev", {});
  const route = routes["POST /v1/route"];
  assert.equal(route.accepts.network, "eip155:8453");
  assert.equal(route.accepts.scheme, "exact");
  assert.equal(route.accepts.price, "$0.01");
  assert.equal(route.accepts.payTo, "0xa47930496923574a33325b9be28fe84fa8d2b1c6");
  assert.equal(route.resource, "https://example.workers.dev/v1/route");
  assert.equal(route.serviceName, "A0 Route Intelligence");
  assert.ok(route.extensions.bazaar);
  assert.equal(route.extensions.bazaar.info.input.type, "http");
  assert.equal(route.extensions.bazaar.info.input.method, "POST");
  assert.equal(route.extensions.bazaar.info.input.bodyType, "json");
  assert.equal(route.extensions.bazaar.info.output.type, "json");
});

test("atomic USDC is rendered without floating-point arithmetic", () => {
  assert.equal(atomicUsdcToDollar("1"), "$0.000001");
  assert.equal(atomicUsdcToDollar("10000"), "$0.01");
  assert.equal(atomicUsdcToDollar("1000000"), "$1");
  assert.equal(atomicUsdcToDollar("1234567"), "$1.234567");
  assert.throws(() => atomicUsdcToDollar("1.5"));
  assert.throws(() => atomicUsdcToDollar("0"));
});

test("rankPeers returns only relevant connected peers", () => {
  const state = {
    peers: {
      a: {
        id: "a",
        name: "Verifier",
        status: "connected",
        capabilities: [{ id: "verification", name: "Verify", tags: ["evidence"] }],
        calls: 1,
        verified_results: 1,
      },
      b: {
        id: "b",
        name: "Coder",
        status: "connected",
        capabilities: [{ id: "coding", name: "Code", tags: ["build"] }],
        calls: 1,
        verified_results: 0,
      },
      c: { id: "c", status: "unreachable", capabilities: [{ id: "verification" }] },
    },
  };
  const rows = rankPeers(state, "verification evidence", 3);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].peer, "a");
});

test("tokenizer deduplicates", () => {
  assert.deepEqual(tokenize("Agent agent ROUTING"), ["agent", "routing"]);
});

test("worker exposes SDK-backed discovery documents", async () => {
  const mod = (await import("../cloudflare/merchant-worker.js")).default;
  const origin = "https://merchant.example";
  const a = await mod.fetch(new Request(origin + "/.well-known/x402"), {});
  assert.equal(a.status, 200);
  const x402 = await a.json();
  assert.equal(x402.x402Version, 2);
  assert.deepEqual(x402.resources, [origin + "/v1/route"]);
  assert.equal(x402.payment_runtime, "@x402/hono");

  const o = await mod.fetch(new Request(origin + "/openapi.json"), {});
  const doc = await o.json();
  assert.equal(doc.paths["/v1/route"].post["x-payment-info"].amount, "0.01");
  assert.equal(doc.paths["/v1/route"].post["x-payment-info"].implementation, "@x402/hono");

  const s = await mod.fetch(new Request(origin + "/skill.md"), {});
  assert.equal(s.status, 200);
  assert.match(await s.text(), /official x402 v2 Hono middleware/);
});

test("worker exposes Agent Card for discovery", async () => {
  const mod = (await import("../cloudflare/merchant-worker.js")).default;
  const origin = "https://merchant.example";
  for (const path of ["/.well-known/agent-card.json", "/.well-known/agent.json"]) {
    const r = await mod.fetch(new Request(origin + path), {});
    assert.equal(r.status, 200);
    const card = await r.json();
    assert.equal(card.name, "A0 Route Intelligence");
    assert.equal(card.url, origin);
    assert.equal(card.skills[0].id, "paid-route-intelligence");
    assert.equal(card.metadata.payment_protocol, "x402-v2");
    assert.equal(card.metadata.payment_runtime, "@x402/hono");
    assert.equal(card.metadata.paid_endpoint, origin + "/v1/route");
  }
});
