import test from "node:test";
import assert from "node:assert/strict";
import {
  atomicUsdcToDollarPrice,
  tokenize,
  rankPeers,
  buildRouteConfig,
  buildApp,
} from "../cloudflare/merchant-worker.js";

test("official x402 route config is Base exact USDC-priced and Bazaar-declared", () => {
  const routes = buildRouteConfig({}, "https://example.workers.dev");
  const route = routes["POST /v1/route"];
  assert.equal(route.accepts.network, "eip155:8453");
  assert.equal(route.accepts.scheme, "exact");
  assert.equal(route.accepts.price, "$0.010000");
  assert.equal(route.accepts.payTo, "0xa47930496923574a33325b9be28fe84fa8d2b1c6");
  assert.equal(route.extensions.bazaar.info.input.type, "http");
  assert.equal(route.extensions.bazaar.info.input.method, "POST");
  assert.equal(route.extensions.bazaar.info.input.bodyType, "json");
  assert.equal(route.extensions.bazaar.info.output.type, "json");
});

test("atomic USDC prices remain exact", () => {
  assert.equal(atomicUsdcToDollarPrice("1"), "$0.000001");
  assert.equal(atomicUsdcToDollarPrice("10000"), "$0.010000");
  assert.equal(atomicUsdcToDollarPrice("2500000"), "$2.500000");
});

test("rankPeers returns only relevant connected peers", () => {
  const state = { peers: {
    a: { id:"a", name:"Verifier", status:"connected", capabilities:[{id:"verification",name:"Verify",tags:["evidence"]}], calls:1, verified_results:1 },
    b: { id:"b", name:"Coder", status:"connected", capabilities:[{id:"coding",name:"Code",tags:["build"]}], calls:1, verified_results:0 },
    c: { id:"c", status:"unreachable", capabilities:[{id:"verification"}] },
  }};
  const rows = rankPeers(state, "verification evidence", 3);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].peer, "a");
});

test("tokenizer deduplicates", () => {
  assert.deepEqual(tokenize("Agent agent ROUTING"), ["agent", "routing"]);
});

test("worker exposes discovery documents without contacting a facilitator", async () => {
  const app = buildApp({}, "https://merchant.example");
  const a = await app.fetch(new Request("https://merchant.example/.well-known/x402"));
  assert.equal(a.status, 200);
  const x402 = await a.json();
  assert.equal(x402.x402Version, 2);
  assert.equal(x402.resources[0].url, "https://merchant.example/v1/route");

  const o = await app.fetch(new Request("https://merchant.example/openapi.json"));
  const doc = await o.json();
  assert.equal(doc.paths["/v1/route"].post["x-payment-info"].amount, "$0.010000");

  const s = await app.fetch(new Request("https://merchant.example/skill.md"));
  assert.equal(s.status, 200);
  assert.match(await s.text(), /official x402 v2 SDK/);
});

test("worker exposes Agent Card with implementation provenance", async () => {
  const app = buildApp({}, "https://merchant.example");
  for (const path of ["/.well-known/agent-card.json", "/.well-known/agent.json"]) {
    const r = await app.fetch(new Request("https://merchant.example" + path));
    assert.equal(r.status, 200);
    const card = await r.json();
    assert.equal(card.name, "A0 Route Intelligence");
    assert.equal(card.url, "https://merchant.example");
    assert.equal(card.skills[0].id, "paid-route-intelligence");
    assert.equal(card.metadata.payment_protocol, "x402-v2");
    assert.equal(card.metadata.x402_implementation, "official-x402-sdk");
    assert.equal(card.metadata.paid_endpoint, "https://merchant.example/v1/route");
  }
});
