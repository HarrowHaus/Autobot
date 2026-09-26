import test from "node:test";
import assert from "node:assert/strict";
import {AgentEconomyMCP} from "../server.js";

function fakeFetch(routes){
  return async (url,opts={})=>{
    const key=`${opts.method||"GET"} ${url.pathname}`;
    const fn=routes[key];
    if(!fn) throw new Error(`unexpected ${key}`);
    const out=fn(url,opts);
    return {ok:out.status>=200&&out.status<300,status:out.status,async text(){return JSON.stringify(out.body??{});}};
  };
}

test("initialize and tool list expose MCP contract",async()=>{
  const s=new AgentEconomyMCP({fetchImpl:async()=>{throw new Error("no network")}});
  const init=await s.handle({jsonrpc:"2.0",id:1,method:"initialize"});
  assert.equal(init.result.serverInfo.name,"rustchain-agent-economy");
  const list=await s.handle({jsonrpc:"2.0",id:2,method:"tools/list"});
  assert.ok(list.result.tools.some(t=>t.name==="rustchain_jobs_browse"));
  assert.ok(list.result.tools.some(t=>t.name==="rustchain_job_deliver"));
});

test("browse and stats are read-only",async()=>{
  const s=new AgentEconomyMCP({fetchImpl:fakeFetch({
    "GET /agent/jobs":(u)=>{assert.equal(u.searchParams.get("status"),"open");return {status:200,body:{jobs:[{job_id:"j1"}]}};},
    "GET /agent/stats":()=>({status:200,body:{total_jobs:1}})
  })});
  assert.equal((await s.call("rustchain_jobs_browse",{})).jobs[0].job_id,"j1");
  assert.equal((await s.call("rustchain_agent_stats",{})).total_jobs,1);
});

test("post claim and deliver bind configured wallet",async()=>{
  const seen=[];
  const s=new AgentEconomyMCP({wallet:"w",fetchImpl:fakeFetch({
    "POST /agent/jobs":(_u,o)=>{seen.push(JSON.parse(o.body));return {status:201,body:{job_id:"j"}};},
    "POST /agent/jobs/j/claim":(_u,o)=>{seen.push(JSON.parse(o.body));return {status:200,body:{ok:true}};},
    "POST /agent/jobs/j/deliver":(_u,o)=>{seen.push(JSON.parse(o.body));return {status:200,body:{ok:true}};}
  })});
  await s.call("rustchain_job_post",{title:"x",category:"code",reward_rtc:3});
  await s.call("rustchain_job_claim",{job_id:"j"});
  await s.call("rustchain_job_deliver",{job_id:"j",deliverable_url:"https://example.invalid"});
  assert.equal(seen[0].poster_wallet,"w");
  assert.equal(seen[1].worker_wallet,"w");
  assert.equal(seen[2].worker_wallet,"w");
});

test("tools/call returns MCP error content without crashing",async()=>{
  const s=new AgentEconomyMCP({fetchImpl:async()=>{throw new Error("offline")}});
  const out=await s.handle({jsonrpc:"2.0",id:5,method:"tools/call",params:{name:"rustchain_agent_stats",arguments:{}}});
  assert.equal(out.result.isError,true);
  assert.match(out.result.content[0].text,/network error/);
});

test("write tools fail before network without wallet",async()=>{
  const s=new AgentEconomyMCP({fetchImpl:async()=>{throw new Error("must not call")}});
  await assert.rejects(()=>s.call("rustchain_job_claim",{job_id:"j"}),/worker wallet required/);
});
