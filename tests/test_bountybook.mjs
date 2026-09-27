import test from "node:test";
import assert from "node:assert/strict";
import { compactJob, prioritize } from "../commerce/bountybook_scan.mjs";

test("BountyBook jobs normalize into earning_cycle-compatible candidates", () => {
  const row = compactJob({
    id: "job_test",
    title: "Build a Python parser",
    category: "code",
    status: "open",
    budget_usdc: 15,
    spec: { instructions: "Write parser.py and tests" },
  });
  assert.equal(row.task_id, "job_test");
  assert.equal(row.claimable, true);
  assert.equal(row.bounty.amount_atomic, "15000000");
  assert.equal(row.bounty.network, "eip155:8453");
  assert.equal(row.funding_evidence, "platform_reported_escrow");
  assert.ok(row.matched_capabilities.includes("coding"));
  assert.equal(row.output_format, "json");
});

test("BountyBook prioritizes higher paid open work and drops closed jobs", () => {
  const rows = prioritize([
    { id: "low", title: "research", category: "research", status: "open", budget_usdc: 2 },
    { id: "closed", title: "code", category: "code", status: "completed", budget_usdc: 100 },
    { id: "high", title: "code", category: "code", status: "open", budget_usdc: 15 },
  ]);
  assert.deepEqual(rows.map(x => x.task_id), ["high", "low"]);
});
