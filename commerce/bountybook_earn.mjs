#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { privateKeyToAccount } from "viem/accounts";

const API = (process.env.BOUNTYBOOK_API_URL || "https://api.bountybook.ai").replace(/\/$/, "");

function fail(message, extra = {}) {
  process.stdout.write(JSON.stringify({ status: "error", error: message, ...extra }, null, 2) + "\n");
  process.exitCode = 1;
}

async function jsonFetch(url, options = {}) {
  const res = await fetch(url, options);
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : {}; } catch { data = { raw: text.slice(0, 2000) }; }
  if (!res.ok) {
    const err = new Error("HTTP " + res.status + " " + url);
    err.status = res.status;
    err.data = data;
    throw err;
  }
  return data;
}

async function authenticate(account) {
  let nonceData;
  try {
    nonceData = await jsonFetch(API + "/auth/nonce?address=" + encodeURIComponent(account.address));
  } catch (error) {
    if (error.status !== 405) throw error;
    nonceData = await jsonFetch(API + "/auth/nonce", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ address: account.address }),
    });
  }
  const nonce = nonceData?.nonce || nonceData?.message;
  if (!nonce || typeof nonce !== "string") throw new Error("BountyBook auth nonce missing");
  const signature = await account.signMessage({ message: nonce });
  const verified = await jsonFetch(API + "/auth/verify", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ address: account.address, signature }),
  });
  if (!verified?.token) throw new Error("BountyBook auth token missing");
  return verified.token;
}

function parseSubmission(plan) {
  const raw = plan?.content;
  if (raw && typeof raw === "object") return raw;
  if (typeof raw === "string") {
    try { return JSON.parse(raw); } catch { return { content: raw }; }
  }
  return { summary: plan?.summary || "SwarmBrain delivery" };
}

function budgetAtomic(job) {
  const n = Number(job?.budget_usdc ?? job?.budget ?? job?.reward_usdc ?? 0);
  return Number.isFinite(n) && n > 0 ? String(Math.round(n * 1_000_000)) : "0";
}

async function getJob(id) {
  const data = await jsonFetch(API + "/jobs/" + encodeURIComponent(id));
  return data?.job || data;
}

async function claimAndSubmit(planPath) {
  const privateKey = String(process.env.BOUNTYBOOK_AGENT_PRIVATE_KEY || "").trim();
  if (!/^0x[0-9a-fA-F]{64}$/.test(privateKey)) {
    throw new Error("BOUNTYBOOK_AGENT_PRIVATE_KEY missing or invalid");
  }
  const plan = JSON.parse(readFileSync(planPath, "utf8"));
  if (!plan?.task_id) throw new Error("plan task_id missing");
  const account = privateKeyToAccount(privateKey);
  const token = await authenticate(account);
  const before = await getJob(plan.task_id);
  const status = String(before?.status || "").toLowerCase();
  if (status && status !== "open") {
    return { status: "not_claimed", reason: "job_not_open", task_id: plan.task_id, job_status: status, worker: account.address };
  }
  const expectedAtomic = String(plan?.bounty_amount_atomic || "0");
  const liveAtomic = budgetAtomic(before);
  if (expectedAtomic !== "0" && liveAtomic !== "0" && expectedAtomic !== liveAtomic) {
    return { status: "not_claimed", reason: "bounty_changed", task_id: plan.task_id, expected_atomic: expectedAtomic, live_atomic: liveAtomic };
  }

  const headers = { "content-type": "application/json", authorization: "Bearer " + token };
  const claim = await jsonFetch(API + "/jobs/" + encodeURIComponent(plan.task_id) + "/claim", {
    method: "POST",
    headers,
    body: JSON.stringify({ executorAddress: account.address, txHash: "0x" }),
  });

  const outputData = parseSubmission(plan);
  let submitted;
  try {
    submitted = await jsonFetch(API + "/jobs/" + encodeURIComponent(plan.task_id) + "/submit", {
      method: "POST",
      headers,
      body: JSON.stringify({ executorAddress: account.address, outputData }),
    });
  } catch (error) {
    return {
      status: "claimed_delivery_failed",
      task_id: plan.task_id,
      worker: account.address,
      claim,
      error: String(error?.message || error),
      details: error?.data || null,
    };
  }

  let current = null;
  for (let i = 0; i < 12; i += 1) {
    await new Promise(resolve => setTimeout(resolve, 5000));
    try { current = await getJob(plan.task_id); } catch { continue; }
    const s = String(current?.status || "").toLowerCase();
    if (["verified", "completed", "paid", "failed", "rejected", "refunded"].includes(s)) break;
  }

  const payout = current?.payout || current?.payment || null;
  const tx = payout?.tx_hash || payout?.txHash || current?.payout_tx_hash || current?.payment_tx_hash || null;
  const finalStatus = String(current?.status || submitted?.status || "submitted").toLowerCase();
  return {
    status: tx && ["verified","completed","paid"].includes(finalStatus) ? "settlement_observed" : "submitted",
    task_id: plan.task_id,
    worker: account.address,
    claim_status: claim?.status || "claimed",
    submit_status: submitted?.status || "submitted",
    job_status: finalStatus,
    payout_transaction: tx,
    advertised_bounty_atomic: expectedAtomic,
    truth_boundary: tx ? "A payout transaction was reported by BountyBook; independently reconcile on Base before counting revenue." : "Submitted work is not earned revenue until payout settlement is observed.",
  };
}

if (process.argv[1]?.endsWith("bountybook_earn.mjs")) {
  const planPath = process.argv[2];
  if (!planPath) {
    fail("usage: node commerce/bountybook_earn.mjs <earn-plan.json>");
  } else {
    try {
      const result = await claimAndSubmit(planPath);
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
    } catch (error) {
      fail(String(error?.message || error), { details: error?.data || null });
    }
  }
}

export { authenticate, claimAndSubmit };
