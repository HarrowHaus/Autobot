import { describe, expect, it } from "vitest";
import { getOrCreateAccountByEmail, creditAccount, getCreditBalance } from "../../src/lib/accounts.js";
import { FakeD1, FakeD1Store } from "../support/fake-d1.js";

/**
 * The Stripe webhook handler in src/index.ts (POST /webhooks/stripe) is
 * gated behind BILLING_ENABLED and, when enabled, behind a real Stripe
 * signature check — reproducing that end-to-end in tests would mean either
 * standing up a real signed Stripe event (extra fixture complexity for a
 * flow that is fully disabled in this alpha) or mocking the Stripe SDK.
 * Neither was judged worth it right now. Instead this test exercises the
 * exact idempotency gate the handler uses — `INSERT OR IGNORE INTO
 * checkout_sessions ... ` keyed on `stripe_session_id`, only crediting the
 * account when `meta.changes > 0` — directly against the fake D1, which is
 * the part of the flow that actually matters for "don't double-credit on a
 * retried webhook delivery". See the final report for this scope decision.
 */
describe("webhook fulfillment idempotency (checkout_sessions INSERT OR IGNORE gate)", () => {
  it("credits an account exactly once even if the same Stripe session is processed twice", async () => {
    const store = new FakeD1Store();
    const db = new FakeD1(store);
    const email = "buyer@example.com";
    const sessionId = "cs_test_123";
    const credits = 10;

    async function fulfill() {
      const inserted = await db
        .prepare(
          `INSERT OR IGNORE INTO checkout_sessions (id, stripe_session_id, kind, credits_granted, status) VALUES (?, ?, ?, ?, 'fulfilled')`
        )
        .bind(`cs_${Math.random()}`, sessionId, "web_credit_pack", credits)
        .run();

      if ((inserted.meta.changes ?? 0) > 0) {
        const accountId = await getOrCreateAccountByEmail(db as unknown as D1Database, email);
        await creditAccount(db as unknown as D1Database, accountId, credits, "purchase", sessionId);
      }
    }

    await fulfill();
    await fulfill(); // simulates Stripe retrying the same webhook delivery

    const accountId = await getOrCreateAccountByEmail(db as unknown as D1Database, email);
    const balance = await getCreditBalance(db as unknown as D1Database, accountId);
    expect(balance).toBe(credits); // not 2x credits
    expect(store.creditLedger).toHaveLength(1);
    expect(store.checkoutSessions).toHaveLength(1);
  });
});
