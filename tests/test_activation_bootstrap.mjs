import test from "node:test";
import assert from "node:assert/strict";
import {
  isBaseAddress,
  parseArgs,
  REPO,
  OPERATIONAL_BRANCH,
} from "../tools/bootstrap_basedagents_identity.mjs";

test("bootstrap recognizes Base/EVM payout addresses", () => {
  assert.equal(isBaseAddress("0x" + "ab".repeat(20)), true);
  assert.equal(isBaseAddress("0x1234"), false);
  assert.equal(isBaseAddress("not-a-wallet"), false);
});

test("bootstrap args preserve explicit wallet and no-run gates", () => {
  const parsed = parseArgs([
    "--wallet", "0x" + "ab".repeat(20),
    "--no-run",
    "--no-github",
  ]);
  assert.equal(parsed.wallet, "0x" + "ab".repeat(20));
  assert.equal(parsed.noRun, true);
  assert.equal(parsed.noGitHub, true);
});

test("bootstrap targets the actual SwarmBrain repository and operational branch", () => {
  assert.equal(REPO, "HarrowHaus/Autobot");
  assert.equal(OPERATIONAL_BRANCH, "claude/monetizable-project-concepts-b97bv2");
});
