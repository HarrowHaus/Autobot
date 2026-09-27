import { Hono } from "hono";
import { paymentMiddleware, x402ResourceServer } from "@x402/hono";
import { HTTPFacilitatorClient } from "@x402/core/server";
import { ExactEvmScheme } from "@x402/evm/exact/server";
import { declareDiscoveryExtension } from "@x402/extensions/bazaar";

const DEFAULTS = {
  network: "eip155:8453",
  asset: "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  payTo: "0xa47930496923574a33325b9be28fe84fa8d2b1c6",
  amount: "10000",
  facilitator: "https://facilitator.x402endpoints.online",
  stateUrl: "https://raw.githubusercontent.com/HarrowHaus/Autobot/refs/heads/claude/monetizable-project-concepts-b97bv2/data/mesh-state.json",
};

const SDK_VERSION = "2.27.0";
const paymentGates = new Map();

export function cfg(env = {}) {
  return {
    network: env.A0_PAYMENT_NETWORK || DEFAULTS.network,
    asset: env.A0_USDC_ASSET || DEFAULTS.asset,
    payTo: env.A0_PAY_TO || DEFAULTS.payTo,
    amount: String(env.A0_ROUTE_PRICE_ATOMIC || DEFAULTS.amount),
    facilitator: (env.A0_FACILITATOR_URL || DEFAULTS.facilitator).replace(/\/$/, ""),
    stateUrl: env.A0_SWARMBRAIN_STATE_URL || DEFAULTS.stateUrl,
  };
}

export function atomicUsdcToDollar(value) {
  const raw = String(value ?? "");
  if (!/^\d+$/.test(raw)) throw new Error("USDC atomic amount must be a non-negative integer");
  const atomic = BigInt(raw);
  if (atomic <= 0n) throw new Error("USDC atomic amount must be positive");
  const whole = atomic / 1_000_000n;
  const fraction = (atomic % 1_000_000n).toString().padStart(6, "0").replace(/0+$/, "");
  return "$" + whole.toString() + (fraction ? "." + fraction : "");
}

export function tokenize(value) {
  return [...new Set(String(value || "").toLowerCase().match(/[a-z0-9]+/g) || [])];
}

export function rankPeers(state, query, limit = 3) {
  const terms = tokenize(query);
  const peers = Object.values(state?.peers || {});
  const rows = [];
  for (const peer of peers) {
    if (!["connected", "card_verified"].includes(peer.status)) continue;
    const caps = (peer.capabilities || []).flatMap(cap => [cap.id, cap.name, ...(cap.tags || [])]);
    const haystack = new Set(tokenize([peer.id, peer.name, peer.kind, peer.region, ...caps].join(" ")));
    const matched = terms.filter(term => haystack.has(term));
    if (matched.length === 0) continue;
    const overlap = matched.length / Math.max(1, terms.length);
    const calls = Number(peer.calls || 0);
    const accepted = Number(peer.verified_results || 0);
    const outcomeWeight = (accepted + 1) / (calls + 2);
    const activation = overlap * (0.5 + outcomeWeight);
    rows.push({
      peer: peer.id,
      name: peer.name || peer.id,
      activation: Number(activation.toFixed(6)),
      matched_terms: matched,
      capabilities: (peer.capabilities || []).map(cap => cap.id || cap.name).filter(Boolean).slice(0, 12),
      protocol_version: peer.protocol_version || null,
      endpoint: peer.endpoint || null,
      observed_reliability: peer.response_reliability ?? null,
    });
  }
  return rows
    .sort((a, b) => b.activation - a.activation || a.peer.localeCompare(b.peer))
    .slice(0, Math.max(1, Math.min(10, Number(limit) || 3)));
}

function routeOutputSchema() {
  return {
    type: "object",
    properties: {
      query: { type: "string" },
      routes: { type: "array" },
      scope: { type: "string" },
      state_coordinator: {},
    },
    required: ["query", "routes", "scope"],
  };
}

export function buildRouteConfig(origin, env = {}) {
  const c = cfg(env);
  const resource = new URL("/v1/route", origin).toString();
  return {
    "POST /v1/route": {
      accepts: {
        scheme: "exact",
        price: atomicUsdcToDollar(c.amount),
        network: c.network,
        payTo: c.payTo,
        maxTimeoutSeconds: 60,
      },
      resource,
      description: "Read-only ranked routing over the SwarmBrain public peer graph",
      mimeType: "application/json",
      serviceName: "A0 Route Intelligence",
      tags: ["agents", "routing", "swarm", "research", "verification"],
      extensions: {
        ...declareDiscoveryExtension({
          method: "POST",
          input: { query: "verification research", limit: 3 },
          inputSchema: {
            type: "object",
            properties: {
              query: { type: "string", description: "Capability or task terms to route" },
              limit: { type: "integer", minimum: 1, maximum: 10 },
            },
            required: ["query"],
          },
          bodyType: "json",
          output: {
            example: {
              query: "verification research",
              routes: [{ peer: "attractor", activation: 0.75 }],
              scope: "read_only_route_selection",
              state_coordinator: null,
            },
            schema: routeOutputSchema(),
          },
        }),
      },
    },
  };
}

function paymentGate(env, origin) {
  const c = cfg(env);
  const key = [origin, c.network, c.payTo.toLowerCase(), c.amount, c.facilitator].join("|");
  if (paymentGates.has(key)) return paymentGates.get(key);

  const facilitator = new HTTPFacilitatorClient({ url: c.facilitator });
  const resourceServer = new x402ResourceServer(facilitator)
    .register(c.network, new ExactEvmScheme());
  const gate = paymentMiddleware(buildRouteConfig(origin, env), resourceServer);
  paymentGates.set(key, gate);
  return gate;
}

async function routeWork(c, query, limit) {
  const response = await fetch(c.stateUrl, {
    headers: { "user-agent": "SwarmBrain-Commerce/1" },
  });
  if (!response.ok) throw new Error("peer_state_unavailable:" + response.status);
  const state = await response.json();
  return {
    query,
    routes: rankPeers(state, query, limit),
    scope: "read_only_route_selection",
    state_coordinator: state.coordinator || null,
  };
}

function noStore(c) {
  c.header("cache-control", "no-store");
}

const app = new Hono();

app.get("/health", c => {
  noStore(c);
  return c.json({
    ok: true,
    service: "a0-route-intelligence",
    payments: "x402-v2",
    payment_runtime: "@x402/hono",
    x402_sdk_version: SDK_VERSION,
    network: cfg(c.env).network,
  });
});

app.get("/catalog", c => {
  noStore(c);
  const config = cfg(c.env);
  return c.json({
    service: "A0 Route Intelligence",
    endpoint: new URL("/v1/route", c.req.url).toString(),
    method: "POST",
    price_atomic: config.amount,
    price_usd: atomicUsdcToDollar(config.amount),
    asset: config.asset,
    network: config.network,
    pay_to: config.payTo,
    facilitator: config.facilitator,
    payment_runtime: "@x402/hono",
    x402_sdk_version: SDK_VERSION,
  });
});

app.get("/.well-known/x402", c => {
  noStore(c);
  return c.json({
    x402Version: 2,
    resources: [new URL("/v1/route", c.req.url).toString()],
    payment_runtime: "@x402/hono",
    sdk_version: SDK_VERSION,
  });
});

for (const path of ["/.well-known/agent-card.json", "/.well-known/agent.json"]) {
  app.get(path, c => {
    noStore(c);
    const config = cfg(c.env);
    const origin = new URL(c.req.url).origin;
    const endpoint = new URL("/v1/route", origin).toString();
    return c.json({
      name: "A0 Route Intelligence",
      description: "Paid read-only routing across the SwarmBrain public peer graph. Returns ranked agent routes for capability or task terms.",
      url: origin,
      protocolVersion: "0.3",
      version: "0.29.0",
      provider: {
        organization: "A0 / SwarmBrain",
        url: "https://github.com/HarrowHaus/Autobot/issues/33",
      },
      capabilities: { streaming: false, pushNotifications: false, stateTransitionHistory: false },
      defaultInputModes: ["application/json", "text/plain"],
      defaultOutputModes: ["application/json"],
      skills: [{
        id: "paid-route-intelligence",
        name: "Paid Agent Route Intelligence",
        description: "Rank known SwarmBrain peers for requested capabilities. Read-only; does not dispatch work.",
        tags: ["routing", "agents", "discovery", "verification", "research", "x402", "USDC", "Base"],
        examples: ["verification research routing", "x402 payment verification routing"],
      }],
      metadata: {
        payment_protocol: "x402-v2",
        payment_runtime: "@x402/hono",
        x402_sdk_version: SDK_VERSION,
        network: config.network,
        asset: "USDC",
        price_atomic: config.amount,
        payment_discovery: new URL("/.well-known/x402", origin).toString(),
        openapi: new URL("/openapi.json", origin).toString(),
        skill_document: new URL("/skill.md", origin).toString(),
        storefront: "https://github.com/HarrowHaus/Autobot/issues/33",
        paid_endpoint: endpoint,
      },
    });
  });
}

app.get("/openapi.json", c => {
  noStore(c);
  const config = cfg(c.env);
  const origin = new URL(c.req.url).origin;
  return c.json({
    openapi: "3.1.0",
    info: {
      title: "A0 Route Intelligence",
      version: "0.29.0",
      description: "Paid read-only routing over the SwarmBrain public peer graph.",
    },
    servers: [{ url: origin }],
    paths: {
      "/v1/route": {
        post: {
          summary: "Rank useful agent routes",
          operationId: "routeAgents",
          requestBody: {
            required: true,
            content: {
              "application/json": {
                schema: {
                  type: "object",
                  properties: {
                    query: { type: "string" },
                    limit: { type: "integer", minimum: 1, maximum: 10 },
                  },
                  required: ["query"],
                },
              },
            },
          },
          responses: {
            "200": { description: "Paid routing result" },
            "400": { description: "Invalid route request" },
            "402": { description: "x402 payment required" },
            "502": { description: "Swarm state unavailable" },
          },
          "x-payment-info": {
            protocols: ["x402"],
            amount: atomicUsdcToDollar(config.amount).slice(1),
            currency: "USDC",
            network: config.network,
            implementation: "@x402/hono",
          },
        },
      },
    },
  });
});

app.get("/skill.md", c => {
  noStore(c);
  return c.text([
    "# A0 Route Intelligence",
    "",
    "Use POST /v1/route with JSON {\"query\":\"capability terms\",\"limit\":3}.",
    "The endpoint uses the official x402 v2 Hono middleware with exact USDC payments on Base.",
    "An unpaid request receives the x402 payment challenge from the SDK middleware.",
    "The service is read-only: it ranks known SwarmBrain peers and does not dispatch work.",
    "Discovery: /.well-known/x402 and /openapi.json.",
  ].join("\n"), 200, {
    "content-type": "text/markdown; charset=utf-8",
    "cache-control": "no-store",
  });
});

app.use("/v1/route", async (c, next) => {
  const origin = new URL(c.req.url).origin;
  return paymentGate(c.env, origin)(c, next);
});

app.post("/v1/route", async c => {
  noStore(c);
  let body;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: "invalid_json" }, 400);
  }
  const query = String(body?.query || "").trim();
  if (!query || query.length > 1000) return c.json({ error: "query_required" }, 400);
  const limit = Math.max(1, Math.min(10, Number(body?.limit) || 3));
  try {
    return c.json(await routeWork(cfg(c.env), query, limit));
  } catch (error) {
    return c.json({
      error: "resource_execution_failed",
      detail: String(error?.message || error).slice(0, 200),
    }, 502);
  }
});

app.notFound(c => {
  noStore(c);
  return c.json({ error: "not_found" }, 404);
});

export default {
  fetch(request, env, executionCtx) {
    return app.fetch(request, env, executionCtx);
  },
};
