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
