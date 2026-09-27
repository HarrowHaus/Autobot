const API = process.env.BOUNTYBOOK_API_URL || "https://api.bountybook.ai";

const CAP_MAP = {
  code: ["coding", "reasoning"],
  research: ["research", "reasoning"],
  data: ["data-analysis", "research"],
  content: ["research", "planning"],
  find: ["research"],
  action: ["planning", "reasoning"],
  growth: ["planning", "research"],
  monitor: ["research", "data-analysis"],
};

function amountAtomic(value) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return "0";
  return String(Math.round(n * 1_000_000));
}

function textOf(job) {
  const spec = typeof job?.spec === "string" ? job.spec : JSON.stringify(job?.spec || {});
  return [job?.title, job?.description, spec, job?.instructions].filter(Boolean).join("\n").slice(0, 12000);
}

function classify(job) {
  const category = String(job?.category || "").toLowerCase();
  const direct = CAP_MAP[category] || [];
  if (direct.length) return direct;
  const text = textOf(job).toLowerCase();
  const caps = new Set();
  if (/python|javascript|typescript|rust|code|script|api|test|jest|github|compile/.test(text)) caps.add("coding");
  if (/research|document|source|compare|framework|find|audit/.test(text)) caps.add("research");
  if (/csv|json|dataset|analy|metric|log|count|statistics/.test(text)) caps.add("data-analysis");
  if (/plan|strategy|outline|workflow/.test(text)) caps.add("planning");
  if (!caps.size) caps.add("reasoning");
  return [...caps];
}

export function compactJob(job) {
  const id = job?.id || job?.job_id || job?.jobId || null;
  const budget = Number(job?.budget_usdc ?? job?.budget ?? job?.reward_usdc ?? 0);
  const status = String(job?.status || "open").toLowerCase();
  const description = textOf(job);
  return {
    task_id: id,
    title: String(job?.title || "BountyBook task").slice(0, 300),
    description,
    category: job?.category || null,
    required_capabilities: classify(job),
    matched_capabilities: classify(job),
    expected_output: job?.success_criteria || job?.spec || job?.instructions || null,
    output_format: "json",
    claimable: status === "open",
    bounty: {
      amount_atomic: amountAtomic(budget),
      amount_display: budget.toFixed(2),
      token: "USDC",
      network: "eip155:8453",
    },
    escrow: { status: status === "open" && budget > 0 ? "funded" : null, deposit_tx_hash: job?.deposit_tx_hash || null },
    funding_evidence: status === "open" && budget > 0 ? "platform_reported_escrow" : "none",
    payment_status: job?.payment_status || null,
    created_at: job?.created_at || job?.createdAt || null,
    source: "https://www.bountybook.ai/job/" + encodeURIComponent(id || ""),
    source_kind: "bountybook",
  };
}

export function prioritize(jobs) {
  return jobs
    .map(compactJob)
    .filter(j => j.task_id && j.claimable && BigInt(j.bounty.amount_atomic || "0") > 0n)
    .sort((a,b) => {
      const av = BigInt(a.bounty.amount_atomic), bv = BigInt(b.bounty.amount_atomic);
      if (av !== bv) return av > bv ? -1 : 1;
      return String(a.task_id).localeCompare(String(b.task_id));
    });
}

export async function scanBountyBook({ apiUrl = API } = {}) {
  const observedAt = new Date().toISOString();
  try {
    const res = await fetch(apiUrl.replace(/\/$/, "") + "/jobs?status=open&limit=100", {
      headers: { accept: "application/json", "user-agent": "SwarmBrain/1.0" },
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const jobs = Array.isArray(data) ? data : Array.isArray(data?.jobs) ? data.jobs : [];
    const candidates = prioritize(jobs);
    return {
      source: "bountybook-public-api",
      api: apiUrl,
      observed_at: observedAt,
      status: "ok",
      tasks_examined: jobs.length,
      candidate_count: candidates.length,
      candidates,
      independently_verified_funding_count: 0,
      settled_external_revenue_atomic: "0",
      truth_boundary: "Open BountyBook listings are platform-reported escrow. Revenue is not earned until the job verifies and USDC payout settles.",
    };
  } catch (error) {
    return {
      source: "bountybook-public-api",
      api: apiUrl,
      observed_at: observedAt,
      status: "unavailable",
      candidate_count: null,
      candidates: [],
      error: String(error?.message || error).slice(0, 500),
      settled_external_revenue_atomic: "0",
    };
  }
}

if (process.argv[1]?.endsWith("bountybook_scan.mjs")) {
  const report = await scanBountyBook();
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  if (report.status !== "ok") process.exitCode = 1;
}
