import test from "node:test";
import assert from "node:assert/strict";
import {tokenize,rankPeers,buildPaymentRequired} from "../cloudflare/merchant-worker.js";

test("payment requirement is Base v2 USDC exact",()=>{
  const r=buildPaymentRequired("https://example.workers.dev/v1/route",{});
  assert.equal(r.x402Version,2);
  assert.equal(r.accepts[0].network,"eip155:8453");
  assert.equal(r.accepts[0].scheme,"exact");
  assert.equal(r.accepts[0].amount,"10000");
  assert.equal(r.extensions.bazaar.info.input.type,"http");
  assert.equal(r.extensions.bazaar.info.output.type,"json");
});
test("rankPeers returns only relevant connected peers",()=>{
  const state={peers:{a:{id:"a",name:"Verifier",status:"connected",capabilities:[{id:"verification",name:"Verify",tags:["evidence"]}],calls:1,verified_results:1},b:{id:"b",name:"Coder",status:"connected",capabilities:[{id:"coding",name:"Code",tags:["build"]}],calls:1,verified_results:0},c:{id:"c",status:"unreachable",capabilities:[{id:"verification"}]}}};
  const rows=rankPeers(state,"verification evidence",3);
  assert.equal(rows.length,1); assert.equal(rows[0].peer,"a");
});
test("tokenizer deduplicates",()=>assert.deepEqual(tokenize("Agent agent ROUTING"),["agent","routing"]));

test("worker exposes discovery documents",async()=>{
  const mod=(await import("../cloudflare/merchant-worker.js")).default;
  const origin="https://merchant.example";
  const a=await mod.fetch(new Request(origin+"/.well-known/x402"),{});
  assert.equal(a.status,200);
  assert.deepEqual((await a.json()).resources,[origin+"/v1/route"]);
  const o=await mod.fetch(new Request(origin+"/openapi.json"),{});
  const doc=await o.json();
  assert.equal(doc.paths["/v1/route"].post["x-payment-info"].amount,"0.01");
  const s=await mod.fetch(new Request(origin+"/skill.md"),{});
  assert.equal(s.status,200);
  assert.match(await s.text(),/x402 v2/);
});


test("worker exposes Agent Card for discovery",async()=>{
  const mod=(await import("../cloudflare/merchant-worker.js")).default;
  const origin="https://merchant.example";
  for(const path of ["/.well-known/agent-card.json","/.well-known/agent.json"]){
    const r=await mod.fetch(new Request(origin+path),{});
    assert.equal(r.status,200);
    const card=await r.json();
    assert.equal(card.name,"A0 Route Intelligence");
    assert.equal(card.url,origin);
    assert.equal(card.skills[0].id,"paid-route-intelligence");
    assert.equal(card.metadata.payment_protocol,"x402-v2");
    assert.equal(card.metadata.paid_endpoint,origin+"/v1/route");
  }
});


test("worker llms.txt cross-links the public directory listing",async()=>{
  const mod=(await import("../cloudflare/merchant-worker.js")).default;
  const r=await mod.fetch(new Request("https://merchant.example/llms.txt"),{});
  assert.equal(r.status,200);
  const body=await r.text();
  assert.match(body,/allagents\.app\/agent\/a0-route-intelligence/);
  assert.match(body,/Paid endpoint:/);
  assert.match(body,/0\.01 USDC/);
});
