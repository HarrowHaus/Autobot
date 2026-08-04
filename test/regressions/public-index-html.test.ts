import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { describe, expect, it } from "vitest";

const here = path.dirname(fileURLToPath(import.meta.url));
const indexHtml = readFileSync(path.resolve(here, "../../public/index.html"), "utf-8");

/**
 * Regression guard for the DOM-XSS fix: the client script must never use
 * innerHTML (or insertAdjacentHTML/outerHTML) with server- or user-derived
 * content. A static source check is a blunt instrument, but it directly
 * guards against someone reintroducing innerHTML in a future edit — the
 * exact mistake this containment pass fixed.
 */
describe("public/index.html — DOM XSS regression", () => {
  it("never assigns innerHTML, outerHTML, or insertAdjacentHTML", () => {
    expect(indexHtml).not.toMatch(/\.innerHTML\s*=/);
    expect(indexHtml).not.toMatch(/\.outerHTML\s*=/);
    expect(indexHtml).not.toMatch(/insertAdjacentHTML/);
  });

  it("does not advertise PayPal support, a QuickBooks/Xero export, or a purchase flow (all removed in this alpha)", () => {
    const lower = indexHtml.toLowerCase();
    expect(lower).not.toContain("paypal");
    // "does not currently produce a ... Xero import file" is an accurate
    // disclaimer, not a claim of support — so check for absence of an
    // active processor/target <select>, not absence of the word itself.
    expect(indexHtml).not.toMatch(/<select[^>]*name=["']target["']/i);
    expect(lower).not.toMatch(/buy\s+credit/);
    expect(lower).not.toContain("pricing");
  });
});
