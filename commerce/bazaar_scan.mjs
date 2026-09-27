import { HTTPFacilitatorClient } from "@x402/core/server";
import { withBazaar } from "@x402/extensions/bazaar";

const DEFAULT_FACILITATOR = "https://facilitator.x402endpoints.online";
const DEFAULT_NETWORK = "eip155:8453";
const DEFAULT_PAY_TO = "0xa47930496923574a33325b9be28fe84fa8d2b1c6";
const DEFAULT_QUERIES = [
  "agent routing",
  "research verification",
  "audio music",
  "art nft",
  "data analysis",
];

function lower(value) {
  return String(value || "").toLowerCase();
}

export function resourcePaysTo(resource, payTo) {
  const target = lower(payTo);
  return Array.isArray(resource?.accepts) &&
    resource.accepts.some(option => lower(option?.payTo) === target);
}

export function compactResource(resource) {
  return {
    resource: resource?.resource || null,
    type: resource?.type || null,
    x402Version: resource?.x402Version ?? null,
    serviceName: resource?.serviceName || null,
    description: resource?.description || null,
    tags: Array.isArray(resource?.tags) ? resource.tags : [],
    accepts: Array.isArray(resource?.accepts)
      ? resource.accepts.map(option => ({
          scheme: option?.scheme || null,
          network: option?.network || null,
          amount: option?.amount || null,
          asset: option?.asset || null,
          payTo: option?.payTo || null,
        }))
      : [],
    lastUpdated: resource?.lastUpdated || null,
    l30DaysTotalCalls: resource?.l30DaysTotalCalls ?? null,
    l30DaysUniquePayers: resource?.l30DaysUniquePayers ?? null,
    lastCalledAt: resource?.lastCalledAt ?? null,
  };
}

export function summarizeList(response, payTo) {
  const items = Array.isArray(response?.items) ? response.items : [];
  const ours = items.filter(item => resourcePaysTo(item, payTo));
  return {
    resources_seen: items.length,
    our_resources_seen: ours.length,
    pagination: response?.pagination || null,
    our_resources: ours.map(compactResource),
  };
}

export async function scanBazaar({
  facilitatorUrl = process.env.A0_FACILITATOR_URL || DEFAULT_FACILITATOR,
  network = process.env.A0_PAYMENT_NETWORK || DEFAULT_NETWORK,
  payTo = process.env.A0_PAY_TO || DEFAULT_PAY_TO,
  queries = (process.env.A0_BAZAAR_QUERIES || "")
    .split(",")
    .map(value => value.trim())
    .filter(Boolean),
} = {}) {
  if (!queries.length) queries = DEFAULT_QUERIES;
  const observedAt = new Date().toISOString();
  const client = withBazaar(new HTTPFacilitatorClient({
    url: facilitatorUrl.replace(/\/$/, ""),
  }));

  const report = {
    source: "x402-official-bazaar-client",
    sdk: "@x402/extensions/bazaar",
    observed_at: observedAt,
    facilitator: facilitatorUrl,
    network,
    pay_to: payTo,
    status: "ok",
    list: null,
    searches: [],
    errors: [],
  };

  try {
    const listed = await client.extensions.bazaar.listResources({
      type: "http",
      network,
      limit: 100,
    });
    report.list = summarizeList(listed, payTo);
  } catch (error) {
    report.errors.push({
      operation: "listResources",
      error: String(error?.message || error).slice(0, 500),
    });
  }

  for (const query of queries) {
    try {
      const result = await client.extensions.bazaar.search({
        query,
        type: "http",
        network,
        limit: 20,
      });
      const resources = Array.isArray(result?.resources) ? result.resources : [];
      report.searches.push({
        query,
        result_count: resources.length,
        partial_results: result?.partialResults ?? null,
        pagination: result?.pagination || null,
        resources: resources.map(compactResource),
      });
    } catch (error) {
      report.searches.push({
        query,
        result_count: null,
        resources: [],
        error: String(error?.message || error).slice(0, 500),
      });
    }
  }

  if (!report.list && report.searches.every(row => row.error)) {
    report.status = "unavailable";
  } else if (report.errors.length || report.searches.some(row => row.error)) {
    report.status = "partial";
  }
  return report;
}

if (process.argv[1]?.endsWith("bazaar_scan.mjs")) {
  scanBazaar()
    .then(report => {
      process.stdout.write(JSON.stringify(report, null, 2) + "\n");
    })
    .catch(error => {
      process.stdout.write(JSON.stringify({
        source: "x402-official-bazaar-client",
        status: "unavailable",
        error: String(error?.message || error).slice(0, 500),
      }, null, 2) + "\n");
      process.exitCode = 1;
    });
}
