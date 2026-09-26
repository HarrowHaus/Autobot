import test from "node:test";
import assert from "node:assert/strict";
import {RustChainAgentEconomy, RustChainAgentEconomyError} from "../src/index.js";

function fakeFetch(routes) {
  return async (url, opts = {}) => {
    const key = `${opts.method || "GET"} ${url.pathname}`;
    const handler = routes[key];
    if (!handler) throw new Error(`unexpected route ${key}`);
    const out = handler(url, opts);
    return {
      ok: out.status >= 200 && out.status < 300,
      status: out.status,
      async text() { return out.text ?? JSON.stringify(out.body ?? {}); },
    };
  };
}

test("browse jobs encodes filters", async () => {
  const client = new RustChainAgentEconomy({
    fetchImpl: fakeFetch({
      "GET /agent/jobs": (url) => {
        assert.equal(url.searchParams.get("status"), "open");
        assert.equal(url.searchParams.get("category"), "code");
        assert.equal(url.searchParams.get("limit"), "5");
        return {status: 200, body: {jobs: [{job_id: "j1"}]}};
      },
    }),
  });
  const out = await client.browseJobs({category: "code", limit: 5});
  assert.equal(out.jobs[0].job_id, "j1");
});

test("post, claim and deliver use configured wallet", async () => {
  const seen = [];
  const client = new RustChainAgentEconomy({
    wallet: "worker-wallet",
    fetchImpl: fakeFetch({
      "POST /agent/jobs": (_u, o) => { seen.push(JSON.parse(o.body)); return {status: 201, body: {job_id: "j1"}}; },
      "POST /agent/jobs/j1/claim": (_u, o) => { seen.push(JSON.parse(o.body)); return {status: 200, body: {ok: true}}; },
      "POST /agent/jobs/j1/deliver": (_u, o) => { seen.push(JSON.parse(o.body)); return {status: 200, body: {ok: true}}; },
    }),
  });
  await client.postJob({title: "Task", category: "code", rewardRtc: 5});
  await client.claimJob("j1");
  await client.deliverJob("j1", {deliverableUrl: "https://example.invalid/result", resultSummary: "done"});
  assert.equal(seen[0].poster_wallet, "worker-wallet");
  assert.equal(seen[0].reward_rtc, 5);
  assert.equal(seen[1].worker_wallet, "worker-wallet");
  assert.equal(seen[2].worker_wallet, "worker-wallet");
});

test("accept, dispute, cancel and reputation are covered", async () => {
  const routes = {};
  for (const [method, path] of [
    ["POST", "/agent/jobs/j1/accept"],
    ["POST", "/agent/jobs/j1/dispute"],
    ["POST", "/agent/jobs/j1/cancel"],
    ["GET", "/agent/reputation/w"],
    ["GET", "/agent/stats"],
    ["GET", "/agent/jobs/j1"],
  ]) routes[`${method} ${path}`] = () => ({status: 200, body: {ok: true}});
  const c = new RustChainAgentEconomy({wallet: "w", fetchImpl: fakeFetch(routes)});
  assert.equal((await c.acceptJob("j1")).ok, true);
  assert.equal((await c.disputeJob("j1", {reason: "bad"})).ok, true);
  assert.equal((await c.cancelJob("j1")).ok, true);
  assert.equal((await c.reputation()).ok, true);
  assert.equal((await c.stats()).ok, true);
  assert.equal((await c.getJob("j1")).ok, true);
});

test("HTTP and JSON errors are explicit", async () => {
  const c1 = new RustChainAgentEconomy({
    fetchImpl: fakeFetch({"GET /agent/stats": () => ({status: 503, body: {error: "offline"}})}),
  });
  await assert.rejects(() => c1.stats(), (e) => e instanceof RustChainAgentEconomyError && e.status === 503);

  const c2 = new RustChainAgentEconomy({
    fetchImpl: fakeFetch({"GET /agent/stats": () => ({status: 200, text: "not-json"})}),
  });
  await assert.rejects(() => c2.stats(), /non-JSON/);
});

test("missing wallet fails before network", async () => {
  const c = new RustChainAgentEconomy({fetchImpl: async () => { throw new Error("must not call network"); }});
  await assert.rejects(() => c.claimJob("j1"), /worker wallet required/);
});
