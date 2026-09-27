import { RegistryClient } from "basedagents";

const DEFAULT_API = "https://api.basedagents.ai";
const DEFAULT_CAPABILITIES = [
  "research",
  "verification",
  "planning",
  "coding",
  "data-analysis",
  "reasoning",
];

function normalize(value) {
  return String(value || "").trim().toLowerCase();
}

export function matchCapabilities(task, capabilities = DEFAULT_CAPABILITIES) {
  const wanted = new Set(capabilities.map(normalize).filter(Boolean));
  const required = Array.isArray(task?.required_capabilities)
    ? task.required_capabilities.map(normalize).filter(Boolean)
    : [];
  return required.filter(capability => wanted.has(capability));
}

export function compactTask(task, capabilities = DEFAULT_CAPABILITIES) {
  const bounty = task?.bounty || null;
  const escrow = task?.escrow || null;
  const matched = matchCapabilities(task, capabilities);
  return {
    task_id: task?.task_id || null,
    title: String(task?.title || "").slice(0, 300),
    description: String(task?.description || "").slice(0, 2000),
    category: task?.category || null,
    required_capabilities: Array.isArray(task?.required_capabilities) ? task.required_capabilities : [],
    matched_capabilities: matched,
    expected_output: task?.expected_output || null,
    output_format: task?.output_format || null,
    claimable: task?.claimable === true,
    bounty: bounty ? {
      amount_atomic: bounty.amount_atomic || null,
      amount_display: bounty.amount_display || null,
      token: bounty.token || null,
      network: bounty.network || null,
    } : null,
    escrow: escrow ? {
      status: escrow.status || null,
      deposit_tx_hash: escrow.deposit_tx_hash || null,
    } : null,
    funding_evidence: escrow?.status === "funded"
      ? "platform_reported_escrow"
      : (bounty ? "advertised_bounty" : "none"),
    payment_status: task?.payment_status || null,
    created_at: task?.created_at || null,
    source: DEFAULT_API + "/v1/tasks/" + encodeURIComponent(task?.task_id || ""),
  };
}

export function prioritize(tasks, capabilities = DEFAULT_CAPABILITIES) {
  return tasks
    .map(task => compactTask(task, capabilities))
    .filter(task => task.bounty && task.claimable)
    .sort((a, b) => {
      const af = a.funding_evidence === "platform_reported_escrow" ? 1 : 0;
      const bf = b.funding_evidence === "platform_reported_escrow" ? 1 : 0;
      if (af !== bf) return bf - af;
      if (a.matched_capabilities.length !== b.matched_capabilities.length) {
        return b.matched_capabilities.length - a.matched_capabilities.length;
      }
      const av = BigInt(a.bounty?.amount_atomic || "0");
      const bv = BigInt(b.bounty?.amount_atomic || "0");
      if (av !== bv) return av > bv ? -1 : 1;
      return String(a.task_id).localeCompare(String(b.task_id));
    });
}

export async function scanBasedAgents({
  apiUrl = process.env.BASEDAGENTS_API_URL || DEFAULT_API,
  capabilities = (process.env.A0_EARNING_CAPABILITIES || "")
    .split(",")
    .map(value => value.trim())
    .filter(Boolean),
} = {}) {
  if (!capabilities.length) capabilities = DEFAULT_CAPABILITIES;
  const client = new RegistryClient(apiUrl.replace(/\/$/, ""));
  const observedAt = new Date().toISOString();
  try {
    const result = await client.getTasks({
      status: "open",
      min_usdc: "0.01",
      limit: 100,
    });
    const tasks = Array.isArray(result?.tasks) ? result.tasks : [];
    const candidates = prioritize(tasks, capabilities);
    return {
      source: "basedagents-official-sdk",
      sdk: "basedagents@0.9.0",
      api: apiUrl,
      observed_at: observedAt,
      status: "ok",
      capabilities,
      tasks_examined: tasks.length,
      candidate_count: candidates.length,
      candidates: candidates.slice(0, 50),
      independently_verified_funding_count: 0,
      settled_external_revenue_atomic: "0",
      truth_boundary: "Marketplace escrow status is platform-reported until independently checked on-chain; an open bounty is not earned revenue.",
    };
  } catch (error) {
    return {
      source: "basedagents-official-sdk",
      sdk: "basedagents@0.9.0",
      api: apiUrl,
      observed_at: observedAt,
      status: "unavailable",
      capabilities,
      candidate_count: null,
      candidates: [],
      independently_verified_funding_count: 0,
      settled_external_revenue_atomic: "0",
      error: String(error?.message || error).slice(0, 500),
    };
  }
}

if (process.argv[1]?.endsWith("basedagents_scan.mjs")) {
  scanBasedAgents()
    .then(report => {
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
      if (report.status !== "ok") process.exitCode = 1;
    })
    .catch(error => {
      process.stdout.write(JSON.stringify({
        source: "basedagents-official-sdk",
        status: "unavailable",
        error: String(error?.message || error).slice(0, 500),
      }, null, 2) + "\n");
      process.exitCode = 1;
    });
}
