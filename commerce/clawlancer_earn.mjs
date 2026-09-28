#!/usr/bin/env node
import { readFileSync } from "node:fs";
import process from "node:process";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const API = (process.env.CLAWLANCER_API_URL || "https://clawlancer.ai/api").replace(/\/$/, "");

function safeJson(text) {
  if (typeof text !== "string") return null;
  try { return JSON.parse(text); } catch { return null; }
}

function resultValue(result) {
  if (result?.structuredContent) return result.structuredContent;
  const texts = Array.isArray(result?.content)
    ? result.content.filter(x => x?.type === "text" && typeof x.text === "string").map(x => x.text)
    : [];
  for (const text of texts) {
    const parsed = safeJson(text);
    if (parsed !== null) return parsed;
  }
  return texts.length ? { text: texts.join("\n") } : result;
}

function deepFind(value, predicate, path = []) {
  if (!value || typeof value !== "object") return null;
  for (const [key, child] of Object.entries(value)) {
    const next = [...path, key];
    if (predicate(key, child, next)) return child;
    if (child && typeof child === "object") {
      const hit = deepFind(child, predicate, next);
      if (hit !== null) return hit;
    }
  }
  return null;
}

function transactionIdFrom(value) {
  const exact = deepFind(value, (key, child, path) => {
    if (typeof child !== "string" || !child.trim()) return false;
    const k = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (k === "transactionid" || k === "txid") return true;
    return path.some(p => String(p).toLowerCase().includes("transaction")) && k === "id";
  });
  if (exact) return String(exact);

  const text = JSON.stringify(value || {});
  const labelled = text.match(/transaction(?:_|\s|-)?id[^a-zA-Z0-9]+([a-zA-Z0-9_-]{8,})/i);
  return labelled?.[1] || null;
}

function toolScore(tool, words) {
  const hay = (String(tool?.name || "") + " " + String(tool?.description || "")).toLowerCase();
  return words.reduce((score, word) => score + (hay.includes(word) ? 1 : 0), 0);
}

export function chooseTool(tools, kind) {
  const rows = Array.isArray(tools) ? tools : [];
  const candidates = rows.map(tool => {
    let score = 0;
    if (kind === "claim") {
      score = toolScore(tool, ["claim", "bounty", "listing"]);
      if (/claim/i.test(tool?.name || "")) score += 5;
    } else if (kind === "deliver") {
      score = toolScore(tool, ["deliver", "submit", "transaction", "work"]);
      if (/(deliver|submit)/i.test(tool?.name || "")) score += 5;
      if (/evidence/i.test(tool?.name || "")) score -= 2;
    }
    return { tool, score };
  }).filter(x => x.score > 0).sort((a, b) => b.score - a.score);
  return candidates[0]?.tool || null;
}

function propertySchema(tool, name) {
  return tool?.inputSchema?.properties?.[name] || {};
}

function valueFor(schema, value, parsed) {
  const type = schema?.type;
  if (type === "object") return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : { content: value };
  if (type === "array") return [value];
  return value;
}

function assignKnown(args, props, names, value, parsed = null) {
  for (const name of names) {
    if (Object.prototype.hasOwnProperty.call(props, name)) {
      args[name] = valueFor(props[name], value, parsed);
      return name;
    }
  }
  return null;
}

export function buildToolArgs(tool, {
  taskId,
  transactionId = "PENDING_TRANSACTION_ID",
  content = "",
  summary = "",
} = {}) {
  const props = tool?.inputSchema?.properties || {};
  const required = Array.isArray(tool?.inputSchema?.required) ? tool.inputSchema.required : [];
  const args = {};
  const parsed = safeJson(content);

  assignKnown(args, props,
    ["listing_id", "listingId", "bounty_id", "bountyId", "task_id", "taskId"],
    taskId);
  assignKnown(args, props,
    ["transaction_id", "transactionId", "tx_id", "txId"],
    transactionId);
  assignKnown(args, props,
    ["content", "delivery", "deliverable", "result", "output", "work", "submission", "delivery_content", "deliveryContent"],
    content, parsed);
  assignKnown(args, props,
    ["message", "notes", "summary", "description"],
    summary || content);
  assignKnown(args, props,
    ["delivery_proof", "deliveryProof", "proof"],
    content, parsed);

  const unresolved = [];
  for (const name of required) {
    if (args[name] !== undefined) continue;
    const lower = name.toLowerCase();
    if ((lower.includes("listing") || lower.includes("bounty") || lower.includes("task")) && lower.includes("id")) {
      args[name] = valueFor(propertySchema(tool, name), taskId, null);
    } else if (lower.includes("transaction") && lower.includes("id")) {
      args[name] = valueFor(propertySchema(tool, name), transactionId, null);
    } else if (/(content|deliver|result|output|work|submission|proof)/.test(lower)) {
      args[name] = valueFor(propertySchema(tool, name), content, parsed);
    } else if (/(message|note|summary|description)/.test(lower)) {
      args[name] = valueFor(propertySchema(tool, name), summary || content, null);
    } else {
      unresolved.push(name);
    }
  }

  return { args, unresolved };
}

async function connectMcp(apiKey) {
  const command = process.platform === "win32" ? "npx.cmd" : "npx";
  const transport = new StdioClientTransport({
    command,
    args: ["-y", "clawlancer-mcp"],
    env: {
      ...process.env,
      CLAWLANCER_API_KEY: apiKey,
    },
    stderr: "pipe",
  });
  const client = new Client({ name: "swarmbrain-clawlancer", version: "1.0.0" });
  await client.connect(transport);
  return { client, transport };
}

export function publicError(value, apiKey = "") {
  // Only retain diagnostic fields; never persist headers, request bodies or stacks.
  if (typeof value === "string") {
    let text = apiKey ? value.split(apiKey).join("[redacted]") : value;
    return text.replace(/clw_[\w-]+/g, "[redacted]")
      .replace(/Bearer\s+\S+/gi, "Bearer [redacted]")
      .replace(/0x[a-fA-F0-9]{64}\b/g, "[redacted]")
      .replace(/eyJ[\w-]+\.[\w-]+\.[\w-]+/g, "[redacted]").slice(0, 1200);
  }
  if (typeof value === "number" || typeof value === "boolean") return value;
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return Object.fromEntries(["error", "message", "code", "details", "reason", "hint"]
    .filter(key => value[key] !== undefined)
    .map(key => [key, publicError(value[key], apiKey)]));
}

export async function authFetch(apiKey, path, { method = "GET", body, fetchImpl = fetch } = {}) {
  const res = await fetchImpl(API + path, {
    method,
    signal: AbortSignal.timeout(30_000),
    headers: {
      accept: "application/json",
      "content-type": "application/json",
      authorization: "Bearer " + apiKey,
      "user-agent": "SwarmBrain/1.0",
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const text = await res.text();
  const data = safeJson(text) ?? { raw: text.slice(0, 2000) };
  if (!res.ok) {
    const error = new Error("HTTP " + res.status + " " + path);
    error.data = publicError(data, apiKey);
    error.httpStatus = res.status;
    throw error;
  }
  return data;
}

async function walletDiagnostic(apiKey) {
  const agentId = process.env.CLAWLANCER_AGENT_ID;
  if (!agentId) return null;
  try {
    const data = await authFetch(apiKey, "/wallet/balance?agent_id=" + encodeURIComponent(agentId));
    const numeric = {};
    const visit = (value, path = []) => {
      if (!value || typeof value !== "object") return;
      for (const [key, child] of Object.entries(value)) {
        const next = [...path, key];
        if (/secret|token|key|seed|phrase|address|owner|wallet_id/i.test(key)) continue;
        if (child && typeof child === "object") visit(child, next);
        else if (typeof child === "number" || typeof child === "boolean" ||
          (typeof child === "string" && /^\d+(\.\d+)?$/.test(child))) {
          numeric[next.join(".")] = child;
        }
      }
    };
    visit(data);
    return numeric;
  } catch (error) {
    return { http_status: error.httpStatus || null, error: error.data || "balance_read_failed" };
  }
}

function transactionsFrom(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.transactions)) return data.transactions;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

function listingIdOf(row) {
  return row?.listing_id || row?.listingId || row?.listing?.id || row?.bounty_id || row?.bountyId || null;
}

function idOf(row) {
  return row?.transaction_id || row?.transactionId || row?.id || null;
}

async function findTransaction(apiKey, taskId) {
  try {
    const data = await authFetch(apiKey, "/transactions");
    const rows = transactionsFrom(data);
    const matches = rows.filter(row => String(listingIdOf(row) || "") === String(taskId));
    return matches[0] || null;
  } catch {
    return null;
  }
}

function statusOf(row) {
  return String(row?.status || row?.state || "").toLowerCase();
}

function planContent(plan) {
  if (typeof plan?.content === "string") return plan.content;
  if (plan?.content !== undefined) return JSON.stringify(plan.content);
  return JSON.stringify({ summary: plan?.summary || "SwarmBrain delivery" });
}

export async function claimDeliver(planPath, { apiKey = process.env.CLAWLANCER_API_KEY } = {}) {
  if (!apiKey || !String(apiKey).startsWith("clw_")) {
    throw new Error("CLAWLANCER_API_KEY missing");
  }
  const plan = JSON.parse(readFileSync(planPath, "utf8"));
  if (!plan?.task_id) throw new Error("plan task_id missing");
  const content = planContent(plan);
  const summary = String(plan?.summary || "SwarmBrain verified delivery").slice(0, 4000);

  const { client, transport } = await connectMcp(apiKey);
  try {
    const listed = await client.listTools();
    const tools = listed?.tools || [];
    const claimTool = chooseTool(tools, "claim");
    const deliverTool = chooseTool(tools, "deliver");
    if (!claimTool) throw new Error("Clawlancer MCP claim tool not found");
    if (!deliverTool) throw new Error("Clawlancer MCP deliver tool not found");

    const claimBuilt = buildToolArgs(claimTool, { taskId: plan.task_id, content, summary });
    if (claimBuilt.unresolved.length) {
      throw new Error("Unsupported required claim fields: " + claimBuilt.unresolved.join(","));
    }
    const deliverPreflight = buildToolArgs(deliverTool, {
      taskId: plan.task_id,
      transactionId: "PENDING_TRANSACTION_ID",
      content,
      summary,
    });
    if (deliverPreflight.unresolved.length) {
      throw new Error("Unsupported required deliver fields: " + deliverPreflight.unresolved.join(","));
    }

    let tx = await findTransaction(apiKey, plan.task_id);
    let claimResult = null;
    let transactionId = idOf(tx);
    const existingStatus = statusOf(tx);
    if (transactionId && ["released", "completed", "paid", "settled"].includes(existingStatus)) {
      return {
        status: "already_released",
        task_id: plan.task_id,
        transaction_id: String(transactionId),
        marketplace_status: existingStatus,
        payout_transaction: tx?.payout_tx_hash || tx?.payoutTxHash || tx?.release_tx_hash || tx?.releaseTxHash || null,
        truth_boundary: "Existing marketplace transaction is already terminal; no duplicate claim or delivery was attempted.",
      };
    }
    if (transactionId && existingStatus === "delivered") {
      return {
        status: "already_delivered",
        task_id: plan.task_id,
        transaction_id: String(transactionId),
        marketplace_status: existingStatus,
        truth_boundary: "Existing marketplace transaction is already delivered; no duplicate claim or delivery was attempted.",
      };
    }

    if (!transactionId) {
      // The official MCP drops everything except data.error on HTTP failure.
      // Make the same documented claim request once, preserving safe diagnostics.
      try {
        claimResult = await authFetch(apiKey, "/listings/" + encodeURIComponent(plan.task_id) + "/claim", {
          method: "POST", body: {},
        });
      } catch (error) {
        return {
          status: "claim_failed",
          task_id: plan.task_id,
          claim_tool: "POST /api/listings/{id}/claim",
          http_status: error.httpStatus || null,
          error: error.data || publicError(String(error.message), apiKey),
          wallet_diagnostic: await walletDiagnostic(apiKey),
        };
      }

      transactionId = transactionIdFrom(claimResult);
      if (!transactionId) {
        tx = await findTransaction(apiKey, plan.task_id);
        transactionId = idOf(tx);
      }
    }
    if (!transactionId) {
      return {
        status: "claimed_transaction_unresolved",
        task_id: plan.task_id,
        claim_tool: claimTool.name,
        claim_result: claimResult,
        truth_boundary: "The claim call returned successfully but no transaction identifier could be resolved; no revenue is claimed.",
      };
    }

    const deliverBuilt = buildToolArgs(deliverTool, {
      taskId: plan.task_id,
      transactionId,
      content,
      summary,
    });
    const deliverRaw = await client.callTool({ name: deliverTool.name, arguments: deliverBuilt.args });
    const deliverResult = resultValue(deliverRaw);
    if (deliverRaw?.isError) {
      return {
        status: "claimed_delivery_failed",
        task_id: plan.task_id,
        transaction_id: transactionId,
        claim_tool: claimTool.name,
        deliver_tool: deliverTool.name,
        error: deliverResult,
      };
    }

    await new Promise(resolve => setTimeout(resolve, 2500));
    tx = await findTransaction(apiKey, plan.task_id);
    const finalStatus = statusOf(tx) || "delivered";
    const payoutTx =
      tx?.payout_tx_hash ||
      tx?.payoutTxHash ||
      tx?.release_tx_hash ||
      tx?.releaseTxHash ||
      tx?.settlement_tx_hash ||
      tx?.settlementTxHash ||
      null;

    return {
      status: ["released", "completed", "paid", "settled"].includes(finalStatus)
        ? "release_observed"
        : "delivered",
      task_id: plan.task_id,
      transaction_id: String(transactionId),
      marketplace_status: finalStatus,
      payout_transaction: payoutTx,
      claim_tool: claimTool.name,
      deliver_tool: deliverTool.name,
      available_mcp_tools: tools.map(t => t.name).sort(),
      advertised_bounty_atomic: String(plan?.bounty_amount_atomic || "0"),
      truth_boundary: payoutTx
        ? "Clawlancer reported a payout/release transaction; independently reconcile it on Base before counting verified external revenue."
        : "Delivery succeeded, but advertised or delivered value is not revenue until release/settlement is observed.",
    };
  } finally {
    try { await client.close(); } catch {}
    try { await transport.close(); } catch {}
  }
}

export function executionExitCode(result) {
  return ["claim_failed", "claimed_delivery_failed", "claimed_transaction_unresolved", "error"]
    .includes(result?.status) ? 1 : 0;
}

if (process.argv[1]?.endsWith("clawlancer_earn.mjs")) {
  const planPath = process.argv[2];
  if (!planPath) {
    process.stdout.write(JSON.stringify({ status: "error", error: "usage: node commerce/clawlancer_earn.mjs <earn-plan.json>" }, null, 2) + "\n");
    process.exitCode = 1;
  } else {
    try {
      const result = await claimDeliver(planPath);
      process.stdout.write(JSON.stringify(result, null, 2) + "\n");
      process.exitCode = executionExitCode(result);
    } catch (error) {
      process.stdout.write(JSON.stringify({
        status: "error",
        error: String(error?.message || error),
        details: error?.data || null,
      }, null, 2) + "\n");
      process.exitCode = 1;
    }
  }
}
