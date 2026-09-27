import test from "node:test";
import assert from "node:assert/strict";
import { resourcePaysTo, summarizeList } from "../commerce/bazaar_scan.mjs";
import { matchCapabilities, compactTask, prioritize } from "../commerce/basedagents_scan.mjs";

test("Bazaar summary only treats exact payTo matches as ours", () => {
  const payTo = "0xabc";
  const response = {
    items: [
      { resource: "https://a", accepts: [{ payTo: "0xAbC", network: "eip155:8453" }] },
      { resource: "https://b", accepts: [{ payTo: "0xdef", network: "eip155:8453" }] },
    ],
    pagination: { total: 2, limit: 100, offset: 0 },
  };
  assert.equal(resourcePaysTo(response.items[0], payTo), true);
  assert.equal(resourcePaysTo(response.items[1], payTo), false);
  const summary = summarizeList(response, payTo);
  assert.equal(summary.resources_seen, 2);
  assert.equal(summary.our_resources_seen, 1);
  assert.equal(summary.our_resources[0].resource, "https://a");
});

test("BasedAgents capability matching uses explicit advertised requirements", () => {
  const task = { required_capabilities: ["research", "image-generation", "coding"] };
  assert.deepEqual(matchCapabilities(task, ["coding", "research"]), ["research", "coding"]);
});

test("BasedAgents candidate preserves funding truth boundary", () => {
  const task = {
    task_id: "task_1",
    title: "Verify a public dataset",
    description: "Check the supplied public records",
    status: "open",
    claimable: true,
    required_capabilities: ["verification", "research"],
    bounty: {
      amount_atomic: "2500000",
      amount_display: "2.50",
      token: "USDC",
      network: "eip155:8453",
    },
    escrow: { status: "funded", deposit_tx_hash: "0x123" },
    payment_status: "pending",
  };
  const row = compactTask(task, ["verification"]);
  assert.equal(row.funding_evidence, "platform_reported_escrow");
  assert.deepEqual(row.matched_capabilities, ["verification"]);
  assert.equal(row.bounty.amount_atomic, "2500000");
});

test("BasedAgents prioritization prefers platform-reported funded and capability-fit tasks", () => {
  const tasks = [
    {
      task_id: "large-unfunded",
      title: "Large",
      description: "",
      claimable: true,
      required_capabilities: ["research"],
      bounty: { amount_atomic: "10000000", amount_display: "10.00", token: "USDC", network: "eip155:8453" },
      escrow: null,
    },
    {
      task_id: "funded-fit",
      title: "Fit",
      description: "",
      claimable: true,
      required_capabilities: ["research", "verification"],
      bounty: { amount_atomic: "1000000", amount_display: "1.00", token: "USDC", network: "eip155:8453" },
      escrow: { status: "funded" },
    },
  ];
  const rows = prioritize(tasks, ["research", "verification"]);
  assert.equal(rows[0].task_id, "funded-fit");
});
