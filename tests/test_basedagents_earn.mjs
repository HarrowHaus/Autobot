import test from "node:test";
import assert from "node:assert/strict";
import {
  validatePlan,
  taskClaimGate,
  ensurePayoutWallet,
  claimAndDeliver,
} from "../commerce/basedagents_earn.mjs";

const plan = {
  task_id: "task_1",
  bounty_amount_atomic: "2500000",
  bounty_network: "eip155:8453",
  summary: "Verified result",
  submission_type: "json",
  content: "{\"ok\":true}",
};

function fundedTask(changes = {}) {
  return {
    task_id: "task_1",
    status: "open",
    claimed_by_agent_id: null,
    claimable: true,
    bounty: { amount_atomic: "2500000", network: "eip155:8453" },
    escrow: { status: "funded" },
    payment_status: "pending",
    ...changes,
  };
}

test("plan validation allows only bounded JSON autodelivery", () => {
  assert.equal(validatePlan(plan).task_id, "task_1");
  assert.throws(() => validatePlan({ ...plan, submission_type: "pr" }), /only_json/);
});

test("claim gate requires funded escrow and unchanged bounty", () => {
  assert.equal(taskClaimGate(fundedTask(), plan, "ag_me").ok, true);
  assert.equal(
    taskClaimGate(fundedTask({ escrow: null }), plan, "ag_me").reason,
    "funded_escrow_required",
  );
  assert.equal(
    taskClaimGate(
      fundedTask({ bounty: { amount_atomic: "3000000", network: "eip155:8453" } }),
      plan,
      "ag_me",
    ).reason,
    "bounty_changed_since_preflight",
  );
});

test("wallet setup reuses existing address without a write", async () => {
  let writes = 0;
  const client = {
    async getWallet() {
      return {
        wallet_address: "0x" + "ab".repeat(20),
        wallet_network: "eip155:8453",
      };
    },
    async updateWallet() {
      writes += 1;
      throw new Error("unexpected");
    },
  };
  const wallet = await ensurePayoutWallet({
    client,
    keypair: {},
    agentId: "ag_me",
    desiredAddress: "",
  });
  assert.equal(wallet.wallet_network, "eip155:8453");
  assert.equal(writes, 0);
});

test("claimAndDeliver claims only after live re-check then delivers", async () => {
  const calls = [];
  const client = {
    async getTask() {
      calls.push("getTask");
      return { task: fundedTask() };
    },
    async getWallet() {
      calls.push("getWallet");
      return {
        wallet_address: "0x" + "ab".repeat(20),
        wallet_network: "eip155:8453",
      };
    },
    async claimTask(_kp, id) {
      calls.push("claim:" + id);
      return { ok: true, task_id: id, status: "claimed" };
    },
    async deliverTask(_kp, id, delivery) {
      calls.push("deliver:" + id);
      return {
        ok: true,
        task_id: id,
        receipt_id: "r1",
        status: "submitted",
        delivery,
      };
    },
  };
  const result = await claimAndDeliver({
    client,
    keypair: {},
    agentId: "ag_me",
    plan,
  });
  assert.equal(result.status, "delivered");
  assert.deepEqual(calls, [
    "getTask",
    "getWallet",
    "claim:task_1",
    "deliver:task_1",
  ]);
});

test("existing submitted work is idempotent and not redelivered", async () => {
  const client = {
    async getTask() {
      return {
        task: fundedTask({
          status: "submitted",
          claimed_by_agent_id: "ag_me",
          payment_status: "pending",
        }),
      };
    },
  };
  const result = await claimAndDeliver({
    client,
    keypair: {},
    agentId: "ag_me",
    plan,
  });
  assert.equal(result.status, "already_delivered");
});
