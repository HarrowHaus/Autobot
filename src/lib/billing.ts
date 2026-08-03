import Stripe from "stripe";
import type { Env } from "../types.js";

export const CREDIT_PACKS = {
  web_1: { credits: 1, amountCents: 200, label: "1 conversion" },
  web_10: { credits: 10, amountCents: 1500, label: "10 conversions" },
  web_50: { credits: 50, amountCents: 6000, label: "50 conversions" },
  api_100: { credits: 100, amountCents: 3000, label: "100 API conversions" },
} as const;

export type PackKey = keyof typeof CREDIT_PACKS;

export function getStripeClient(env: Env): Stripe | null {
  if (!env.STRIPE_SECRET_KEY) return null;
  return new Stripe(env.STRIPE_SECRET_KEY, {
    httpClient: Stripe.createFetchHttpClient(),
  });
}

export async function createCreditPackCheckoutSession(
  stripe: Stripe,
  pack: PackKey,
  email: string,
  successUrl: string,
  cancelUrl: string
): Promise<Stripe.Checkout.Session> {
  const config = CREDIT_PACKS[pack];
  return stripe.checkout.sessions.create({
    mode: "payment", // one-time payment only — no subscriptions anywhere in this product
    customer_email: email,
    line_items: [
      {
        quantity: 1,
        price_data: {
          currency: "usd",
          unit_amount: config.amountCents,
          product_data: { name: `PayoutSplit — ${config.label}` },
        },
      },
    ],
    metadata: { pack, credits: String(config.credits), email },
    success_url: successUrl,
    cancel_url: cancelUrl,
  });
}
