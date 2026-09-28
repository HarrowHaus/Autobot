#!/usr/bin/env node
const API = (process.env.CLAWLANCER_API_URL || "https://clawlancer.ai/api").replace(/\/$/, "");
const API_KEY = String(process.env.CLAWLANCER_API_KEY || "").trim();
const AGENT_ID = String(process.env.CLAWLANCER_AGENT_ID || "03d091cd-48ca-4f9a-928d-80e4223f4ca8").trim();
const PAYOUT_WALLET = String(process.env.CLAWLANCER_PAYOUT_WALLET || "0x97f10389bb589422220bab9a76a43b0b4b9d1926").trim();

function isAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test(String(value || "").trim());
}

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    ...options,
    headers: {
      accept: "application/json",
      authorization: "Bearer " + API_KEY,
      ...(options.body ? { "content-type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const text = await res.text();
  let data;
  try { data = text ? JSON.parse(text) : {}; }
  catch { data = { raw: text.slice(0, 2000) }; }
  if (!res.ok) {
    const err = new Error("HTTP " + res.status + " " + path);
    err.data = data;
    throw err;
  }
  return data;
}

function extractAgent(data) {
  return data?.agent || data?.data || data;
}

function walletOf(agent) {
  return String(
    agent?.wallet_address ??
    agent?.walletAddress ??
    agent?.wallet ??
    ""
  ).trim();
}

async function main() {
  if (!API_KEY.startsWith("clw_")) throw new Error("CLAWLANCER_API_KEY missing");
  if (!AGENT_ID) throw new Error("CLAWLANCER_AGENT_ID missing");
  if (!isAddress(PAYOUT_WALLET)) throw new Error("CLAWLANCER_PAYOUT_WALLET is not a valid EVM address");

  let current = null;
  try {
    current = extractAgent(await api("/agents/" + encodeURIComponent(AGENT_ID)));
  } catch {}

  const before = walletOf(current);
  if (before && before.toLowerCase() === PAYOUT_WALLET.toLowerCase()) {
    console.log(JSON.stringify({
      status: "already_configured",
      agent_id: AGENT_ID,
      wallet_address: PAYOUT_WALLET,
    }, null, 2));
    return;
  }

  let updated;
  try {
    updated = extractAgent(await api("/agents/me", {
      method: "PATCH",
      body: JSON.stringify({ wallet_address: PAYOUT_WALLET }),
    }));
  } catch (first) {
    updated = extractAgent(await api("/agents/" + encodeURIComponent(AGENT_ID), {
      method: "PATCH",
      body: JSON.stringify({ wallet_address: PAYOUT_WALLET }),
    }));
  }

  const after = walletOf(updated) || PAYOUT_WALLET;
  if (after.toLowerCase() !== PAYOUT_WALLET.toLowerCase()) {
    throw new Error("Clawlancer wallet update returned an unexpected address");
  }

  console.log(JSON.stringify({
    status: "updated",
    agent_id: AGENT_ID,
    wallet_address: PAYOUT_WALLET,
    previous_wallet_present: Boolean(before),
  }, null, 2));
}

main().catch(error => {
  console.error(JSON.stringify({
    status: "error",
    error: String(error?.message || error),
    details: error?.data || null,
  }, null, 2));
  process.exitCode = 1;
});
