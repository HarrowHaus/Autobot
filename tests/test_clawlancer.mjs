import test from "node:test";
import assert from "node:assert/strict";
import { compactListing, prioritize } from "../commerce/clawlancer_scan.mjs";
import { chooseTool, buildToolArgs } from "../commerce/clawlancer_earn.mjs";

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
