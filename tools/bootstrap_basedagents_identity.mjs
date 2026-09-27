#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { pathToFileURL } from "node:url";
import { createInterface } from "node:readline/promises";
import { spawnSync } from "node:child_process";
import process from "node:process";
import {
  RegistryClient,
  deserializeKeypair,
  generateKeypair,
  publicKeyToAgentId,
  serializeKeypair,
} from "basedagents";

export const REPO = "HarrowHaus/Autobot";
export const OPERATIONAL_BRANCH = "claude/monetizable-project-concepts-b97bv2";
export const DEFAULT_API = "https://api.basedagents.ai";
export const DEFAULT_KEYPAIR_PATH = join(
  homedir(),
  ".basedagents",
  "keys",
  "swarmbrain-harrow-keypair.json",
);

export const PROFILE = {
  name: "SwarmBrain-Harrow",
  description:
    "SwarmBrain commerce coordinator: routes research, verification, planning, coding, data-analysis and reasoning work across a persistent peer network and can fulfill bounded paid tasks.",
  capabilities: [
    "research",
    "verification",
    "planning",
    "coding",
    "data-analysis",
    "reasoning",
  ],
  protocols: ["https", "a2a", "x402"],
  organization: "HarrowHaus",
  version: "0.1.0",
  tags: ["commerce", "routing", "research", "verification"],
};

export function isBaseAddress(value) {
  return /^0x[a-fA-F0-9]{40}$/.test(String(value || "").trim());
}

export function parseArgs(argv) {
  const out = {
    wallet: process.env.A0_PAYOUT_WALLET || "",
    api: process.env.BASEDAGENTS_API_URL || DEFAULT_API,
    keypair: DEFAULT_KEYPAIR_PATH,
    noGitHub: false,
    noRun: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--wallet") out.wallet = argv[++i] || "";
    else if (arg === "--api") out.api = argv[++i] || DEFAULT_API;
    else if (arg === "--keypair") out.keypair = resolve(argv[++i] || DEFAULT_KEYPAIR_PATH);
    else if (arg === "--no-github") out.noGitHub = true;
    else if (arg === "--no-run") out.noRun = true;
    else if (arg === "--help" || arg === "-h") out.help = true;
    else throw new Error("Unknown argument: " + arg);
  }
  return out;
}

function help() {
  return [
    "SwarmBrain BasedAgents earning activation",
    "",
    "Usage:",
    "  npm run activate:earning",
    "  npm run activate:earning -- --wallet 0xYOUR_BASE_ADDRESS",
    "",
    "Options:",
    "  --wallet <0x...>      Base mainnet payout address you control",
    "  --api <url>           BasedAgents API (default: https://api.basedagents.ai)",
    "  --keypair <path>      Override local keypair path",
    "  --no-github           Register/bind only; do not upload GitHub Actions secrets",
    "  --no-run              Do not trigger the earning workflow after activation",
    "",
    "The private key is saved locally with restricted file permissions and is never printed.",
  ].join("\n");
}

function gh(args, input = undefined) {
  return spawnSync("gh", args, {
    input,
    encoding: "utf8",
    stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
}

export function githubCliReady() {
  const check = gh(["auth", "status"]);
  return !check.error && check.status === 0;
}

async function getOrRegister(client, keypairPath) {
  let keypair;
  let serialized;

  if (existsSync(keypairPath)) {
    serialized = readFileSync(keypairPath, "utf8").trim();
    keypair = deserializeKeypair(serialized);
    const agentId = publicKeyToAgentId(keypair.publicKey);
    try {
      const agent = await client.getAgent(agentId);
      return { keypair, serialized, agent, created: false, keypairPath };
    } catch {
      process.stdout.write("Local SwarmBrain key exists but is not registered on this API; registering it now.\n");
    }
  } else {
    keypair = await generateKeypair();
    serialized = serializeKeypair(keypair);
  }

  process.stdout.write("Registering SwarmBrain-Harrow with BasedAgents proof-of-work");
  let last = 0;
  const agent = await client.register(keypair, PROFILE, {
    onProgress: attempts => {
      if (attempts - last >= 250000) {
        last = attempts;
        process.stdout.write(".");
      }
    },
  });
  process.stdout.write(" done.\n");

  mkdirSync(dirname(keypairPath), { recursive: true, mode: 0o700 });
  writeFileSync(keypairPath, serialized + "\n", { mode: 0o600 });
  return { keypair, serialized, agent, created: true, keypairPath };
}

async function askWallet(current) {
  if (isBaseAddress(current)) return current.trim();
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  try {
    const answer = await rl.question(
      "Paste the Base mainnet 0x payout address YOU control (do not paste a seed phrase/private key): ",
    );
    return answer.trim();
  } finally {
    rl.close();
  }
}

function setGithubSecret(name, value) {
  const result = gh(["secret", "set", name, "--repo", REPO], value);
  if (result.status !== 0) {
    throw new Error(
      "gh secret set " + name + " failed: " + String(result.stderr || result.stdout).trim(),
    );
  }
}

function triggerEarningWorkflow() {
  const result = gh([
    "workflow",
    "run",
    "commercial_earn.yml",
    "--repo",
    REPO,
    "--ref",
    OPERATIONAL_BRANCH,
  ]);
  if (result.status !== 0) {
    throw new Error(
      "Workflow activation failed: " + String(result.stderr || result.stdout).trim(),
    );
  }
}

export async function activate(options) {
  const wallet = await askWallet(options.wallet);
  if (!isBaseAddress(wallet)) {
    throw new Error("That is not a valid 20-byte EVM/Base address.");
  }

  const client = new RegistryClient(String(options.api).replace(/\/$/, ""));
  const identity = await getOrRegister(client, options.keypair);
  const agentId = publicKeyToAgentId(identity.keypair.publicKey);

  const currentWallet = await client.getWallet(agentId);
  if (
    currentWallet?.wallet_address &&
    currentWallet.wallet_address.toLowerCase() !== wallet.toLowerCase()
  ) {
    throw new Error(
      "This BasedAgents identity already has a different payout wallet. Refusing to silently replace it.",
    );
  }

  const bound =
    currentWallet?.wallet_address
      ? currentWallet
      : await client.updateWallet(identity.keypair, {
          wallet_address: wallet,
          wallet_network: "eip155:8453",
        });

  let github = "not_requested";
  let workflow = "not_requested";

  if (!options.noGitHub) {
    if (githubCliReady()) {
      setGithubSecret("BASEDAGENTS_KEYPAIR_JSON", identity.serialized);
      setGithubSecret("A0_PAYOUT_WALLET", wallet);
      github = "secrets_set";
      if (!options.noRun) {
        triggerEarningWorkflow();
        workflow = "triggered";
      }
    } else {
      github = "manual_required";
    }
  }

  return {
    status: "activated",
    basedagents_agent_id: agentId,
    basedagents_profile: "https://registry.basedagents.ai/agents/" + encodeURIComponent(agentId),
    payout_wallet: bound.wallet_address,
    payout_network: bound.wallet_network || "eip155:8453",
    keypair_path: identity.keypairPath,
    keypair_created: identity.created,
    github,
    workflow,
  };
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    console.log(help());
    return;
  }
  const result = await activate(options);
  console.log("\nActivation result:");
  console.log(JSON.stringify(result, null, 2));
  if (result.github === "manual_required") {
    console.log("\nGitHub CLI is not authenticated, so the private identity was NOT uploaded anywhere.");
    console.log("Use the manual GitHub Secret steps in docs/ACTIVATE_EARNING.md.");
  }
  console.log("\nDo not fund this wallet just to receive BasedAgents bounties.");
}

const invoked = process.argv[1]
  ? pathToFileURL(resolve(process.argv[1])).href === import.meta.url
  : false;

if (invoked) {
  main().catch(error => {
    console.error("\nActivation failed:", String(error?.message || error));
    process.exitCode = 1;
  });
}
