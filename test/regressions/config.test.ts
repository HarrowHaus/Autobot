import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const read = (p: string) => readFileSync(path.resolve(here, "../..", p), "utf-8");

const wranglerToml = read("wrangler.toml");
const packageJson = JSON.parse(read("package.json"));

/**
 * These flags gate the two things in this project that can cause real
 * financial harm. A test is a weak lock, but it makes flipping one a
 * deliberate act with a visible diff rather than a quiet edit.
 */
describe("wrangler.toml safety flags", () => {
  it("keeps BILLING_ENABLED false", () => {
    expect(wranglerToml).toMatch(/^BILLING_ENABLED\s*=\s*"false"$/m);
  });

  it("keeps ALLOW_QBO_EXPORT false", () => {
    expect(wranglerToml).toMatch(/^ALLOW_QBO_EXPORT\s*=\s*"false"$/m);
  });

  it("has no scheduled/cron triggers", () => {
    expect(wranglerToml).not.toContain("[triggers]");
    expect(wranglerToml).not.toContain("crons");
  });
});

describe("dependencies", () => {
  it("does not depend on the Stripe SDK — there is no billing code to need it", () => {
    const all = { ...packageJson.dependencies, ...packageJson.devDependencies };
    expect(Object.keys(all)).not.toContain("stripe");
  });

  it("does not run a landing-page generator on dev or deploy", () => {
    expect(packageJson.scripts.deploy).not.toContain("generate");
    expect(packageJson.scripts.dev).not.toContain("generate");
    expect(packageJson.scripts["generate:pages"]).toBeUndefined();
  });
});

describe("the Worker exposes no billing or account surface", () => {
  const indexTs = read("src/index.ts");

  it.each(["/billing", "/webhooks/stripe", "/v1/convert"])("does not route %s", (route) => {
    expect(indexTs).not.toContain(route);
  });

  it("does not import account, API-key, or billing modules", () => {
    expect(indexTs).not.toMatch(/from "\.\/lib\/(accounts|apikeys|billing)\.js"/);
  });
});
