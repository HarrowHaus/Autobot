import { readFileSync } from "node:fs";
import {
  RegistryClient,
  deserializeKeypair,
  publicKeyToAgentId,
} from "basedagents";

const DEFAULT_API = "https://api.basedagents.ai";
const WALLET_RE = /^0x[a-fA-F0-9]{40}$/;

export function keypairFromEnv(env = process.env) {
  if (env.BASEDAGENTS_KEYPAIR_JSON) {
    return deserializeKeypair(env.BASEDAGENTS_KEYPAIR_JSON);
  }
  if (env.BASEDAGENTS_BOT_PUBLIC_KEY && env.BASEDAGENTS_BOT_PRIVATE_KEY) {
    return deserializeKeypair(JSON.stringify({
      publicKey: env.BASEDAGENTS_BOT_PUBLIC_KEY.trim(),
      privateKey: env.BASEDAGENTS_BOT_PRIVATE_KEY.trim(),
    }));
  }
  return null;
}

export function validatePlan(plan) {
  if (!plan || typeof plan !== "object") throw new Error("plan_required");
  if (!String(plan.task_id || "").trim()) throw new Error("task_id_required");
  if (!String(plan.summary || "").trim()) throw new Error("summary_required");
  if (String(plan.summary).length > 2000) throw new Error("summary_too_long");
  if (plan.submission_type !== "json") throw new Error("only_json_autodelivery_supported");
  if (typeof plan.content !== "string" || !plan.content.trim()) throw new Error("content_required");
  if (plan.content.length > 100_000) throw new Error("content_too_large");
  if (plan.bounty_amount_atomic && !/^\d+$/.test(String(plan.bounty_amount_atomic))) {
    throw new Error("invalid_expected_bounty");
  }
  return plan;
}

export async function ensurePayoutWallet({
  client,
  keypair,
  agentId,
  desiredAddress,
  network = "eip155:8453",
  allowChange = false,
}) {
  const id = agentId || publicKeyToAgentId(keypair.publicKey);
  const current = await client.getWallet(id);
  const desired = String(desiredAddress || "").trim();

  if (current?.wallet_address) {
    if (current.wallet_network && current.wallet_network !== network) {
      if (!desired || !allowChange) throw new Error("payout_wallet_network_mismatch");
    } else if (!desired || current.wallet_address.toLowerCase() === desired.toLowerCase()) {
      return current;
    } else if (!allowChange) {
      throw new Error("payout_wallet_change_requires_explicit_allow");
    }
  }

  if (!desired) throw new Error("payout_wallet_required");
  if (!WALLET_RE.test(desired)) throw new Error("invalid_payout_wallet");
  return client.updateWallet(keypair, {
    wallet_address: desired,
    wallet_network: network,
  });
}

export function taskClaimGate(task, plan, agentId) {
  if (!task) return { ok: false, reason: "task_missing" };
  if (task.claimed_by_agent_id && task.claimed_by_agent_id !== agentId) {
    return { ok: false, reason: "claimed_by_other_agent" };
  }
  if (task.status === "submitted" && task.claimed_by_agent_id === agentId) {
    return { ok: true, alreadyDelivered: true };
  }
  if (["verified", "closed", "cancelled"].includes(task.status)) {
    return { ok: false, reason: "task_terminal" };
  }
  if (task.status !== "open" && !(task.status === "claimed" && task.claimed_by_agent_id === agentId)) {
    return { ok: false, reason: "task_not_open" };
  }
  if (!task.bounty || !/^\d+$/.test(String(task.bounty.amount_atomic || ""))) {
    return { ok: false, reason: "paid_bounty_required" };
  }
  if (BigInt(task.bounty.amount_atomic) <= 0n) {
    return { ok: false, reason: "positive_bounty_required" };
  }
  if (task.escrow?.status !== "funded") {
    return { ok: false, reason: "funded_escrow_required" };
  }
  if (task.status === "open" && task.claimable !== true) {
    return { ok: false, reason: "task_not_claimable" };
  }
  if (plan.bounty_amount_atomic &&
      String(task.bounty.amount_atomic) !== String(plan.bounty_amount_atomic)) {
    return { ok: false, reason: "bounty_changed_since_preflight" };
  }
  if (plan.bounty_network &&
      String(task.bounty.network || task.bounty_network || "") !== String(plan.bounty_network)) {
    return { ok: false, reason: "bounty_network_changed_since_preflight" };
  }
  return { ok: true, alreadyClaimed: task.status === "claimed" };
}

export async function claimAndDeliver({
  client,
  keypair,
  plan,
  payoutWallet,
  allowWalletChange = false,
  agentId,
}) {
  validatePlan(plan);
  const id = agentId || publicKeyToAgentId(keypair.publicKey);
  const detail = await client.getTask(plan.task_id);
  const task = detail?.task;
  const gate = taskClaimGate(task, plan, id);
  if (!gate.ok) {
    return { status: "not_executed", task_id: plan.task_id, reason: gate.reason };
  }
  if (gate.alreadyDelivered) {
    return {
      status: "already_delivered",
      task_id: plan.task_id,
      agent_id: id,
      payment_status: task.payment_status || null,
      payment_tx_hash: task.payment_tx_hash || null,
    };
  }

  const network = String(task.bounty?.network || task.bounty_network || plan.bounty_network || "eip155:8453");
  const wallet = await ensurePayoutWallet({
    client,
    keypair,
    agentId: id,
    desiredAddress: payoutWallet,
    network,
    allowChange: allowWalletChange,
  });

  let claim = null;
  if (!gate.alreadyClaimed) {
    claim = await client.claimTask(keypair, plan.task_id);
  }

  try {
    const delivery = await client.deliverTask(keypair, plan.task_id, {
      summary: String(plan.summary).slice(0, 2000),
      submission_type: "json",
      content: plan.content,
      artifact_urls: Array.isArray(plan.artifact_urls) ? plan.artifact_urls.slice(0, 10) : undefined,
      commit_hash: plan.commit_hash || undefined,
      pr_url: plan.pr_url || undefined,
    });
    return {
      status: "delivered",
      task_id: plan.task_id,
      agent_id: id,
      payout_wallet: wallet.wallet_address,
      payout_network: wallet.wallet_network || network,
      bounty_amount_atomic: String(task.bounty.amount_atomic),
      bounty_network: network,
      claim,
      delivery,
    };
  } catch (error) {
    return {
      status: "claimed_delivery_failed",
      task_id: plan.task_id,
      agent_id: id,
      payout_wallet: wallet.wallet_address,
      bounty_amount_atomic: String(task.bounty.amount_atomic),
      claim,
      error: String(error?.message || error).slice(0, 1000),
      retry_same_task: true,
    };
  }
}

export async function reconcileTasks({ client, taskIds }) {
  const rows = [];
  for (const taskId of taskIds) {
    try {
      const detail = await client.getTask(taskId);
      const payment = await client.getTaskPayment(taskId);
      const task = detail?.task || {};
      rows.push({
        task_id: taskId,
        status: task.status || null,
        claimed_by_agent_id: task.claimed_by_agent_id || null,
        bounty: task.bounty || null,
        payment_status: task.payment_status || payment?.payment_status || null,
        payment_tx_hash: task.payment_tx_hash || payment?.payment_tx_hash || null,
        settled_at: task.settled_at || null,
        escrow: task.escrow || payment?.escrow || null,
      });
    } catch (error) {
      rows.push({
        task_id: taskId,
        status: "lookup_failed",
        error: String(error?.message || error).slice(0, 500),
      });
    }
  }
  return { observed_at: new Date().toISOString(), tasks: rows };
}

async function main() {
  const command = process.argv[2];
  const api = process.env.BASEDAGENTS_API_URL || DEFAULT_API;
  const client = new RegistryClient(api.replace(/\/$/, ""));

  if (command === "claim-deliver") {
    const path = process.argv[3];
    if (!path) throw new Error("usage: basedagents_earn.mjs claim-deliver <plan.json>");
    const keypair = keypairFromEnv(process.env);
    if (!keypair) {
      process.stdout.write(JSON.stringify({
        status: "blocked",
        reason: "basedagents_identity_secret_missing",
        task_id: JSON.parse(readFileSync(path, "utf8")).task_id || null,
      }, null, 2) + "\n");
      return;
    }
    const plan = JSON.parse(readFileSync(path, "utf8"));
    const result = await claimAndDeliver({
      client,
      keypair,
      plan,
      payoutWallet: process.env.A0_PAYOUT_WALLET || "",
      allowWalletChange: process.env.A0_ALLOW_PAYOUT_WALLET_CHANGE === "1",
    });
    process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    return;
  }

  if (command === "reconcile") {
    const ids = process.argv.slice(3).filter(Boolean);
    if (!ids.length) throw new Error("usage: basedagents_earn.mjs reconcile <task-id>...");
    process.stdout.write(JSON.stringify(await reconcileTasks({ client, taskIds: ids }), null, 2) + "\n");
    return;
  }

  throw new Error("usage: basedagents_earn.mjs <claim-deliver|reconcile> ...");
}

if (process.argv[1]?.endsWith("basedagents_earn.mjs")) {
  main().catch(error => {
    process.stdout.write(JSON.stringify({
      status: "failed",
      error: String(error?.message || error).slice(0, 1000),
    }, null, 2) + "\n");
    process.exitCode = 1;
  });
}
