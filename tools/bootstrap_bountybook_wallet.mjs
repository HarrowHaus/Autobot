#!/usr/bin/env node
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import { spawnSync } from "node:child_process";
import { generatePrivateKey, privateKeyToAccount } from "viem/accounts";

const REPO = "HarrowHaus/Autobot";
const BRANCH = "claude/monetizable-project-concepts-b97bv2";
const WALLET_PATH = join(homedir(), ".swarmbrain", "bountybook-wallet.json");

function gh(args, input) {
  const bin = process.platform === "win32" ? "gh.exe" : "gh";
  return spawnSync(bin, args, {
    input,
    encoding: "utf8",
    stdio: input === undefined ? ["ignore", "pipe", "pipe"] : ["pipe", "pipe", "pipe"],
    windowsHide: true,
  });
}

function ghReady() {
  const r = gh(["auth", "status"]);
  return !r.error && r.status === 0;
}

function setSecret(name, value) {
  const r = gh(["secret", "set", name, "--repo", REPO], value);
  if (r.status !== 0) throw new Error(String(r.stderr || r.stdout || "gh secret set failed").trim());
}

function trigger() {
  const r = gh(["workflow", "run", "bountybook_earn.yml", "--repo", REPO, "--ref", BRANCH]);
  if (r.status !== 0) throw new Error(String(r.stderr || r.stdout || "workflow trigger failed").trim());
}

function loadOrCreate() {
  if (existsSync(WALLET_PATH)) {
    const saved = JSON.parse(readFileSync(WALLET_PATH, "utf8"));
    if (!/^0x[0-9a-fA-F]{64}$/.test(String(saved.privateKey || ""))) throw new Error("Saved BountyBook wallet file is invalid.");
    const account = privateKeyToAccount(saved.privateKey);
    return { privateKey: saved.privateKey, address: account.address, created: false };
  }
  const privateKey = generatePrivateKey();
  const account = privateKeyToAccount(privateKey);
  mkdirSync(dirname(WALLET_PATH), { recursive: true, mode: 0o700 });
  writeFileSync(WALLET_PATH, JSON.stringify({ address: account.address, privateKey }, null, 2) + "\n", { mode: 0o600 });
  return { privateKey, address: account.address, created: true };
}

try {
  const wallet = loadOrCreate();
  let github = "manual_required";
  let workflow = "not_requested";
  if (ghReady()) {
    setSecret("BOUNTYBOOK_AGENT_PRIVATE_KEY", wallet.privateKey);
    setSecret("BOUNTYBOOK_AGENT_ADDRESS", wallet.address);
    github = "secrets_set";
    trigger();
    workflow = "triggered";
  }
  console.log(JSON.stringify({
    status: "activated",
    worker_address: wallet.address,
    wallet_file: WALLET_PATH,
    wallet_created: wallet.created,
    github,
    workflow,
    note: "This is a dedicated worker wallet. Never paste its private key into chat or commit it.",
  }, null, 2));
} catch (error) {
  console.error(JSON.stringify({ status: "error", error: String(error?.message || error) }, null, 2));
  process.exitCode = 1;
}
