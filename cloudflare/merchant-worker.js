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
  productUrl: "https://raw.githubusercontent.com/HarrowHaus/Autobot/refs/heads/merchantbrain-opportunity-factory/reports/merchantbrain/product.json",
};

function cfg(env = {}) {
  return {
    network: env.A0_PAYMENT_NETWORK || DEFAULTS.network,
    asset: env.A0_USDC_ASSET || DEFAULTS.asset,
    payTo: env.A0_PAY_TO || DEFAULTS.payTo,
    amount: String(env.A0_ROUTE_PRICE_ATOMIC || DEFAULTS.amount),
    facilitator: (env.A0_FACILITATOR_URL || DEFAULTS.facilitator).replace(/\/$/, ""),
    stateUrl: env.A0_SWARMBRAIN_STATE_URL || DEFAULTS.stateUrl,
    productUrl: env.A0_PRODUCT_URL || DEFAULTS.productUrl,
  };
}

export function atomicUsdcToDollarPrice(value) {
  const atomic = BigInt(String(value));
  if (atomic <= 0n) throw new Error("A0_ROUTE_PRICE_ATOMIC must be positive");
  const whole = atomic / 1000000n;
  const fraction = String(atomic % 1000000n).padStart(6, "0");
  return "$" + whole.toString() + "." + fraction;
}

export function tokenize(value) {
  return [...new Set(String(value || "").toLowerCase().match(/[a-z0-9]+/g) || [])];
}

export function rankPeers(state, query, limit = 3) {
  const terms = tokenize(query);
  const peers = Object.values(state?.peers || {});
  const rows = [];
  for (const p of peers) {
    if (!["connected", "card_verified"].includes(p.status)) continue;
    const caps = (p.capabilities || []).flatMap(c => [c.id, c.name, ...(c.tags || [])]);
    const hay = tokenize([p.id, p.name, p.kind, p.region, ...caps].join(" "));
    const h = new Set(hay);
    const matched = terms.filter(t => h.has(t));
    if (matched.length === 0) continue;
    const overlap = matched.length / Math.max(1, terms.length);
    const calls = Number(p.calls || 0);
    const accepted = Number(p.verified_results || 0);
    const outcome = (accepted + 1) / (calls + 2);
    const activation = overlap * (0.5 + outcome);
    rows.push({
      peer: p.id,
      name: p.name || p.id,
      activation: Number(activation.toFixed(6)),
      matched_terms: matched,
      capabilities: (p.capabilities || []).map(c => c.id || c.name).filter(Boolean).slice(0, 12),
      protocol_version: p.protocol_version || null,
      endpoint: p.endpoint || null,
      observed_reliability: p.response_reliability ?? null,
    });
  }
  return rows
    .sort((a, b) => b.activation - a.activation || a.peer.localeCompare(b.peer))
    .slice(0, Math.max(1, Math.min(10, Number(limit) || 3)));
}

export function buildRouteConfig(env = {}, origin = "https://merchant.invalid") {
  const c = cfg(env);
  const resource = new URL("/v1/route", origin).toString();
  const productResource = new URL("/v1/product", origin).toString();
  return {
    "POST /v1/route": {
      accepts: {
        scheme: "exact",
        price: atomicUsdcToDollarPrice(c.amount),
        network: c.network,
        payTo: c.payTo,
        maxTimeoutSeconds: 60,
      },
      resource,
      description: "Read-only ranked routing over the SwarmBrain peer graph",
      mimeType: "application/json",
      serviceName: "A0 Route Intelligence",
      tags: ["agents", "routing", "swarm", "x402", "discovery"],
      extensions: {
        ...declareDiscoveryExtension({
          method: "POST",
          input: { query: "verification", limit: 3 },
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
              query: "verification",
              routes: [{ peer: "attractor", activation: 0.75 }],
              scope: "read_only_route_selection",
            },
            schema: {
              type: "object",
              properties: {
                query: { type: "string" },
                routes: { type: "array" },
                scope: { type: "string" },
              },
              required: ["query", "routes", "scope"],
            },
          },
        }),
      },
    },
    "POST /v1/product": {
      accepts: { scheme: "exact", price: atomicUsdcToDollarPrice(c.amount), network: c.network, payTo: c.payTo, maxTimeoutSeconds: 60 },
      resource: productResource,
      description: "Latest autonomously selected MerchantBrain digital signal pack",
      mimeType: "application/json",
      serviceName: "MerchantBrain Product",
      tags: ["agents","merchant","research","signals","x402"],
      extensions: {
        ...declareDiscoveryExtension({
          method: "POST", input: {},
          inputSchema: { type: "object", properties: {} }, bodyType: "json",
          output: { example: { status: "publishable", title: "Signal Pack", payload: {} }, schema: { type: "object" } },
        }),
      },
    },
  };
}

async function routeWork(c, query, limit) {
  const response = await fetch(c.stateUrl, {
    headers: { "user-agent": "A0-merchant-worker/0.29" },
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

function buildAgentCard(origin, env) {
  const c = cfg(env);
  const endpoint = new URL("/v1/route", origin).toString();
  return {
    name: "A0 Route Intelligence",
    description: "Paid read-only routing across the SwarmBrain public peer graph. Returns ranked agent routes for capability/task terms.",
    url: origin,
    protocolVersion: "0.3",
    version: "0.29.0",
    provider: {
      organization: "A0 / SwarmBrain",
      url: "https://github.com/HarrowHaus/Autobot/issues/33",
    },
    capabilities: {
      streaming: false,
      pushNotifications: false,
      stateTransitionHistory: false,
    },
    defaultInputModes: ["application/json", "text/plain"],
    defaultOutputModes: ["application/json"],
    skills: [{
      id: "paid-route-intelligence",
      name: "Paid Agent Route Intelligence",
      description: "Rank known agent peers for requested capabilities. Read-only; does not dispatch work.",
      tags: ["routing", "agents", "discovery", "verification", "research", "x402", "USDC", "Base"],
      examples: ["verification research routing", "x402 payment verification routing"],
    }],
    metadata: {
      payment_protocol: "x402-v2",
      x402_implementation: "official-x402-sdk",
      network: c.network,
      asset: "USDC",
      price_atomic: c.amount,
      payment_discovery: new URL("/.well-known/x402", origin).toString(),
      openapi: new URL("/openapi.json", origin).toString(),
      skill_document: new URL("/skill.md", origin).toString(),
      storefront: "https://github.com/HarrowHaus/Autobot/issues/33",
      paid_endpoint: endpoint,
    },
  };
}

export function buildApp(env = {}, origin = "https://merchant.invalid") {
  const c = cfg(env);
  const app = new Hono();
  const facilitator = new HTTPFacilitatorClient({ url: c.facilitator });
  const server = new x402ResourceServer(facilitator)
    .register(c.network, new ExactEvmScheme());

  // The official x402 middleware owns challenge creation, PaymentPayload parsing,
  // verification, settlement and Bazaar extension handling. syncFacilitatorOnStart
  // stays false so a Cloudflare Worker does not perform outbound I/O at module load.
  app.use(paymentMiddleware(buildRouteConfig(env, origin), server, undefined, undefined, false));

  app.get("/health", context => context.json({
    ok: true,
    service: "a0-route-intelligence",
    payments: "x402-v2",
    x402_implementation: "official-x402-sdk",
    network: c.network,
  }));

  app.get("/catalog", context => context.json({
    service: "A0 Route Intelligence",
    endpoint: new URL("/v1/route", origin).toString(),
    method: "POST",
    price_atomic: c.amount,
    price: atomicUsdcToDollarPrice(c.amount),
    asset: c.asset,
    network: c.network,
    pay_to: c.payTo,
    facilitator: c.facilitator,
  }));

  app.get("/.well-known/x402", context => context.json({
    x402Version: 2,
    resources: [{
      url: new URL("/v1/route", origin).toString(),
      method: "POST",
      description: "Paid read-only SwarmBrain route intelligence",
      network: c.network,
      price: atomicUsdcToDollarPrice(c.amount),
    }],
  }));

  app.get("/.well-known/agent-card.json", context => context.json(buildAgentCard(origin, env)));
  app.get("/.well-known/agent.json", context => context.json(buildAgentCard(origin, env)));

  app.get("/openapi.json", context => context.json({
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
            "402": { description: "x402 payment required" },
          },
          "x-payment-info": {
            protocols: ["x402"],
            amount: atomicUsdcToDollarPrice(c.amount),
            currency: "USDC",
            network: c.network,
          },
        },
      },
    },
  }));

  app.get("/skill.md", context => context.text([
    "# A0 Route Intelligence",
    "",
    "Use POST /v1/route with JSON {\"query\":\"capability terms\",\"limit\":3}.",
    "The endpoint uses the official x402 v2 SDK with exact USDC payments on Base.",
    "An unpaid request returns HTTP 402 using the official x402 middleware.",
    "The service is read-only: it ranks known SwarmBrain peers and does not dispatch work.",
    "Discovery: /.well-known/x402, /.well-known/agent-card.json, /openapi.json.",
  ].join("\n"), 200, { "content-type": "text/markdown; charset=utf-8" }));

  app.post("/v1/product", async context => {
    try {
      const response = await fetch(c.productUrl, { headers: { "user-agent": "MerchantBrain-product-delivery/1.0" } });
      if (!response.ok) return context.json({ error: "product_unavailable", status: response.status }, 502);
      const product = await response.json();
      if (product?.status !== "publishable") return context.json({ error: "no_product_published" }, 404);
      return context.json(product);
    } catch (error) {
      return context.json({ error: "product_delivery_failed", detail: String(error?.message || error).slice(0, 200) }, 502);
    }
  });

  app.post("/v1/route", async context => {
    let body;
    try {
      body = await context.req.json();
    } catch {
      return context.json({ error: "invalid_json" }, 400);
    }
    const query = String(body?.query || "").trim();
    if (!query || query.length > 1000) return context.json({ error: "query_required" }, 400);
    const limit = Math.max(1, Math.min(10, Number(body?.limit) || 3));
    try {
      return context.json(await routeWork(c, query, limit));
    } catch (error) {
      return context.json({
        error: "resource_execution_failed",
        detail: String(error?.message || error).slice(0, 200),
      }, 502);
    }
  });

  return app;
}

export default {
  fetch(request, env, executionContext) {
    const origin = new URL(request.url).origin;
    return buildApp(env, origin).fetch(request, env, executionContext);
  },
};
