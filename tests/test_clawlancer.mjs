import test from "node:test";
import assert from "node:assert/strict";
import { compactListing, prioritize } from "../commerce/clawlancer_scan.mjs";
import { chooseTool, buildToolArgs, authFetch, publicError, executionExitCode } from "../commerce/clawlancer_earn.mjs";
import { buildWelcomePlan } from "../commerce/clawlancer_welcome_plan.mjs";

test("claim failure preserves HTTP diagnostics without retrying or leaking credentials", async () => {
  let calls = 0;
  const apiKey = "clw_test_only_not_a_real_secret";
  const fetchImpl = async (_url, options) => {
    calls++;
    assert.equal(options.method, "POST");
    assert.equal(options.body, "{}");
    return new Response(JSON.stringify({
      error: "Failed to create on-chain escrow",
      details: { code: "insufficient_funds", message: `Rejected ${apiKey}`, headers: { authorization: apiKey } },
      stack: "must not be logged",
    }), { status: 500 });
  };
  await assert.rejects(authFetch(apiKey, "/listings/test/claim", { method: "POST", body: {}, fetchImpl }), error => {
    assert.equal(error.httpStatus, 500);
    assert.equal(error.data.details.code, "insufficient_funds");
    assert.equal(error.data.details.message, "Rejected [redacted]");
    assert.equal(error.data.stack, undefined);
    assert.equal(error.data.details.headers, undefined);
    return true;
  });
  assert.equal(calls, 1);
});

test("diagnostics redact key-shaped values and failed execution exits nonzero", () => {
  assert.equal(publicError("Bearer token123"), "Bearer [redacted]");
  assert.equal(publicError("0x" + "a".repeat(64)), "[redacted]");
  for (const status of ["claim_failed", "claimed_delivery_failed", "claimed_transaction_unresolved", "error"]) {
    assert.equal(executionExitCode({ status }), 1);
  }
  for (const status of ["delivered", "already_delivered", "release_observed", "already_released"]) {
    assert.equal(executionExitCode({ status }), 0);
  }
});

test("Clawlancer bounty normalizes into earning-cycle shape", () => {
  const row = compactListing({
    id: "listing-1",
    title: "Backend utility",
    description: "Write Python code and tests",
    category: "coding",
    listing_type: "BOUNTY",
    status: "active",
    price: "8000000",
  });
  assert.equal(row.task_id, "listing-1");
  assert.equal(row.claimable, true);
  assert.equal(row.bounty.amount_atomic, "8000000");
  assert.equal(row.bounty.network, "eip155:8453");
  assert.equal(row.funding_evidence, "platform_reported_escrow");
  assert.ok(row.matched_capabilities.includes("coding"));
  assert.equal(row.output_format, "json");
});

test("Clawlancer prioritizes higher-value claimable bounties", () => {
  const rows = prioritize([
    { id: "low", title: "Research note", category: "research", status: "active", price: "500000" },
    { id: "closed", title: "Closed code", category: "coding", status: "completed", price: "9000000" },
    { id: "high", title: "Code package", category: "coding", status: "active", price: "8000000" },
  ]);
  assert.deepEqual(rows.map(x => x.task_id), ["high", "low"]);
});

test("MCP adapter selects claim and deliver tools from dynamic catalog", () => {
  const tools = [
    { name: "browse_bounties", description: "browse work", inputSchema: { type: "object", properties: {} } },
    { name: "claim_bounty", description: "claim a marketplace listing", inputSchema: { type: "object", properties: { listing_id: { type: "string" } }, required: ["listing_id"] } },
    { name: "deliver_work", description: "deliver transaction work", inputSchema: { type: "object", properties: { transaction_id: { type: "string" }, content: { type: "string" } }, required: ["transaction_id", "content"] } },
  ];
  assert.equal(chooseTool(tools, "claim").name, "claim_bounty");
  assert.equal(chooseTool(tools, "deliver").name, "deliver_work");
});

test("MCP adapter maps tool schemas before any claim", () => {
  const claim = {
    inputSchema: {
      type: "object",
      properties: { listing_id: { type: "string" } },
      required: ["listing_id"],
    },
  };
  const deliver = {
    inputSchema: {
      type: "object",
      properties: {
        transactionId: { type: "string" },
        result: { type: "object" },
        notes: { type: "string" },
      },
      required: ["transactionId", "result"],
    },
  };

  const c = buildToolArgs(claim, { taskId: "abc", content: '{"ok":true}', summary: "done" });
  assert.deepEqual(c.unresolved, []);
  assert.equal(c.args.listing_id, "abc");

  const d = buildToolArgs(deliver, {
    taskId: "abc",
    transactionId: "tx-1",
    content: '{"ok":true}',
    summary: "done",
  });
  assert.deepEqual(d.unresolved, []);
  assert.equal(d.args.transactionId, "tx-1");
  assert.deepEqual(d.args.result, { ok: true });
  assert.equal(d.args.notes, "done");
});

test("MCP adapter refuses unknown required fields before claiming", () => {
  const tool = {
    inputSchema: {
      type: "object",
      properties: { mystery_token: { type: "string" } },
      required: ["mystery_token"],
    },
  };
  const built = buildToolArgs(tool, { taskId: "abc", content: "x" });
  assert.deepEqual(built.unresolved, ["mystery_token"]);
});


test("rook welcome bounty gets a deterministic private-safe plan", () => {
  const plan = buildWelcomePlan({
    candidates: [{
      task_id: "welcome-rook",
      title: "Welcome to Clawlancer! Introduce yourself, rook",
      bounty: { amount_atomic: "10000", network: "eip155:8453" },
      source: "https://clawlancer.ai/marketplace/welcome-rook",
    }],
  }, "rook");
  assert.ok(plan);
  assert.equal(plan.task_id, "welcome-rook");
  assert.equal(plan.primary_peer, "local-deterministic");
  const payload = JSON.parse(plan.content);
  assert.equal(payload.name, "rook");
  assert.ok(payload.skills.includes("coding"));
  assert.match(payload.introduction, /research/i);
  assert.doesNotMatch(plan.content, /TEETHBOX|Donald|family|wife|daughter/i);
});

test("welcome planner ignores another agent's welcome task", () => {
  const plan = buildWelcomePlan({
    candidates: [{
      task_id: "welcome-other",
      title: "Welcome to Clawlancer! Introduce yourself, OtherAgent",
      bounty: { amount_atomic: "10000", network: "eip155:8453" },
    }],
  }, "rook");
  assert.equal(plan, null);
});
