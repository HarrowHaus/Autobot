const API = (process.env.CLAWLANCER_API_URL || "https://clawlancer.ai/api").replace(/\/$/, "");

const CAPABILITY_PATTERNS = [
  ["coding", /\b(code|coding|python|javascript|typescript|rust|api|schema|validator|test|debug|backend|frontend|cli|script)\b/i],
  ["research", /\b(research|compare|brief|report|source|investigate|trend|protocol|framework|audit|docs?)\b/i],
  ["data-analysis", /\b(data|dataset|csv|json|analysis|metric|tvl|fees?|throughput|statistics|on-chain|wallet activity)\b/i],
  ["planning", /\b(plan|strategy|roadmap|workflow|architecture|design)\b/i],
  ["verification", /\b(verify|verification|validate|audit|review|check|qa)\b/i],
  ["reasoning", /\b(explain|assess|evaluate|compare|recommend|reason)\b/i],
];

const CATEGORY_CAPS = {
  coding: ["coding", "reasoning"],
  research: ["research", "reasoning"],
  analysis: ["data-analysis", "research", "reasoning"],
  data: ["data-analysis", "research"],
  writing: ["research", "planning"],
  design: ["planning", "reasoning"],
  other: ["reasoning"],
};

function arrayFromResponse(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.listings)) return data.listings;
  if (Array.isArray(data?.data)) return data.data;
  if (Array.isArray(data?.results)) return data.results;
  return [];
}

function textOf(row) {
  return [
    row?.title,
    row?.name,
    row?.description,
    row?.requirements,
    row?.deliverables,
    row?.instructions,
    Array.isArray(row?.skills) ? row.skills.join(" ") : row?.skills,
    Array.isArray(row?.tags) ? row.tags.join(" ") : row?.tags,
  ].filter(Boolean).join("\n").slice(0, 14000);
}

function capabilities(row) {
  const out = new Set(CATEGORY_CAPS[String(row?.category || "").toLowerCase()] || []);
  const text = textOf(row);
  for (const [cap, pattern] of CAPABILITY_PATTERNS) {
    if (pattern.test(text)) out.add(cap);
  }
  if (!out.size) out.add("reasoning");
  return [...out];
}

function atomicAmount(row) {
  const raw =
    row?.price_atomic ??
    row?.price_wei ??
    row?.bounty_atomic ??
    row?.amount_atomic ??
    row?.price ??
    row?.amount ??
    "0";
  const text = String(raw ?? "").trim();
  if (/^\d+$/.test(text)) return text;
  return "0";
}

function normalizeStatus(row) {
  return String(row?.status || row?.state || "active").toLowerCase();
}

function isClaimable(row) {
  const status = normalizeStatus(row);
  if (row?.claimable === false || row?.available === false) return false;
  if (["closed", "completed", "cancelled", "canceled", "expired", "claimed", "sold", "inactive"].includes(status)) return false;
  return true;
}

export function compactListing(row) {
  const id = row?.id || row?.listing_id || row?.listingId || null;
  const amount = atomicAmount(row);
  const caps = capabilities(row);
  const title = String(row?.title || row?.name || "Clawlancer bounty").slice(0, 300);
  const description = textOf(row);
  return {
    task_id: id,
    title,
    description,
    category: row?.category || null,
    required_capabilities: caps,
    matched_capabilities: caps,
    expected_output: row?.deliverables || row?.requirements || row?.instructions || description,
    output_format: "json",
    claimable: isClaimable(row),
    bounty: {
      amount_atomic: amount,
      amount_display: (Number(amount || "0") / 1_000_000).toFixed(6),
      token: "USDC",
      network: "eip155:8453",
    },
    escrow: {
      status: isClaimable(row) && BigInt(amount || "0") > 0n ? "funded" : null,
      deposit_tx_hash: row?.escrow_tx_hash || row?.escrowTxHash || null,
    },
    funding_evidence: isClaimable(row) && BigInt(amount || "0") > 0n
      ? "platform_reported_escrow"
      : "none",
    payment_status: row?.payment_status || null,
    created_at: row?.created_at || row?.createdAt || null,
    source: "https://clawlancer.ai/marketplace/" + encodeURIComponent(id || ""),
    source_kind: "clawlancer",
    seller: row?.seller?.name || row?.seller_name || row?.seller || null,
  };
}

export function prioritize(rows) {
  return rows
    .map(compactListing)
    .filter(row => row.task_id && row.claimable && BigInt(row.bounty.amount_atomic || "0") > 0n)
    .sort((a, b) => {
      const av = BigInt(a.bounty.amount_atomic || "0");
      const bv = BigInt(b.bounty.amount_atomic || "0");
      if (av !== bv) return av > bv ? -1 : 1;
      if (a.matched_capabilities.length !== b.matched_capabilities.length) {
        return b.matched_capabilities.length - a.matched_capabilities.length;
      }
      return String(a.task_id).localeCompare(String(b.task_id));
    });
}

export async function scanClawlancer({
  apiUrl = API,
  apiKey = process.env.CLAWLANCER_API_KEY || "",
  agentName = process.env.CLAWLANCER_AGENT_NAME || "",
} = {}) {
  const observedAt = new Date().toISOString();
  try {
    const res = await fetch(apiUrl + "/listings?listing_type=BOUNTY", {
      headers: {
        accept: "application/json",
        "user-agent": "SwarmBrain/1.0",
      },
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    const listings = arrayFromResponse(data);

    let transactions = [];
    if (apiKey) {
      try {
        const txRes = await fetch(apiUrl + "/transactions", {
          headers: {
            accept: "application/json",
            authorization: "Bearer " + apiKey,
            "user-agent": "SwarmBrain/1.0",
          },
        });
        if (txRes.ok) {
          const txData = await txRes.json();
          transactions = Array.isArray(txData)
            ? txData
            : Array.isArray(txData?.transactions)
              ? txData.transactions
              : Array.isArray(txData?.data)
                ? txData.data
                : Array.isArray(txData?.results)
                  ? txData.results
                  : [];
        }
      } catch {}
    }

    const terminal = new Set(["delivered", "released", "completed", "paid", "settled", "refunded", "cancelled", "canceled", "disputed"]);
    const txByListing = new Map();
    for (const tx of transactions) {
      const listingId = tx?.listing_id || tx?.listingId || tx?.listing?.id || tx?.bounty_id || tx?.bountyId || null;
      if (!listingId) continue;
      txByListing.set(String(listingId), String(tx?.status || tx?.state || "").toLowerCase());
    }

    let candidates = prioritize(listings).filter(row => !terminal.has(txByListing.get(String(row.task_id))));
    const normalizedAgent = String(agentName || "").trim().toLowerCase();
    if (normalizedAgent) {
      candidates = candidates.sort((a, b) => {
        const at = String(a?.title || "").toLowerCase();
        const bt = String(b?.title || "").toLowerCase();
        const aw = at.includes("welcome to clawlancer") && at.includes(normalizedAgent) ? 1 : 0;
        const bw = bt.includes("welcome to clawlancer") && bt.includes(normalizedAgent) ? 1 : 0;
        if (aw !== bw) return bw - aw;
        const av = BigInt(a?.bounty?.amount_atomic || "0");
        const bv = BigInt(b?.bounty?.amount_atomic || "0");
        if (av !== bv) return av > bv ? -1 : 1;
        return String(a.task_id).localeCompare(String(b.task_id));
      });
    }

    return {
      source: "clawlancer-official-rest-api",
      api: apiUrl,
      observed_at: observedAt,
      status: "ok",
      capabilities: ["research", "verification", "planning", "coding", "data-analysis", "reasoning"],
      tasks_examined: listings.length,
      owned_transaction_count: transactions.length,
      terminal_transaction_excluded_count: [...txByListing.values()].filter(status => terminal.has(status)).length,
      candidate_count: candidates.length,
      candidates: candidates.slice(0, 100),
      independently_verified_funding_count: 0,
      settled_external_revenue_atomic: "0",
      truth_boundary: "Clawlancer documents bounties as pre-funded, but an advertised bounty is not revenue. Count revenue only after a released/settled transaction is observed.",
    };
  } catch (error) {
    return {
      source: "clawlancer-official-rest-api",
      api: apiUrl,
      observed_at: observedAt,
      status: "unavailable",
      candidate_count: null,
      candidates: [],
      independently_verified_funding_count: 0,
      settled_external_revenue_atomic: "0",
      error: String(error?.message || error).slice(0, 500),
    };
  }
}

if (process.argv[1]?.endsWith("clawlancer_scan.mjs")) {
  const report = await scanClawlancer();
  process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  if (report.status !== "ok") process.exitCode = 1;
}
