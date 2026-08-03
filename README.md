# PayoutSplit

Converts Stripe/PayPal payout and transaction exports into QuickBooks Online / Xero-ready journal-entry and bank-match files. Pay-per-use, no signup, no subscription — positioned against subscription incumbents (A2X, Synder, Webgility) rather than competing with them.

See [`plan`](https://github.com/harrowhaus/autobot) commit history / PR description for the full validation research behind this product.

## How it works

Single Cloudflare Worker (Hono). Uploaded CSVs are parsed, grouped by payout, and mapped to two output files entirely in memory — nothing is ever persisted to disk, R2, or a database. Only usage metadata (never file content) goes into D1.

```
src/parsers/{stripe,paypal}.ts     raw CSV -> NormalizedTransaction[]
src/mappers/{qbo,xero}-*.ts        grouped payouts -> target CSV
src/engine.ts                      orchestrates parse -> group -> map
src/index.ts                       Hono routes (/convert, /v1/convert, /webhooks/stripe)
src/growth-loop.ts                 weekly cron: detects new-pair demand signals
```

## Local development

```
npm install
npm run dev          # wrangler dev, regenerates landing pages first
npm test              # vitest
npm run typecheck
```

## Deployment

Deploys via Cloudflare's Git integration ("Workers Builds") on push to `main` — connected directly in the Cloudflare dashboard (Workers & Pages → Import a repository), no GitHub secrets involved. Build command: `npm run generate:pages`. GitHub Actions (`.github/workflows/test.yml`) only runs tests/typecheck; it doesn't deploy.

Manual deploy: `npm run deploy` (requires `wrangler login` or `CLOUDFLARE_API_TOKEN` in the local shell).

No credentials at all? `./scripts/preview-deploy.sh` spins up a fully-working preview (real D1 + KV, schema applied) on a throwaway anonymous Cloudflare account via `wrangler deploy --temporary` — no login required. It expires in about an hour unless claimed via the URL the script prints, and its data store is separate from the real one.

## Required secrets for full functionality

Set via `wrangler secret put <NAME>` (or the Cloudflare dashboard: Worker → Settings → Variables and Secrets):

- `STRIPE_SECRET_KEY` — enables `/billing/checkout` and credit purchases. Without it, billing routes return `501 billing_not_configured` and only the one free trial conversion works.
- `STRIPE_WEBHOOK_SECRET` — enables `/webhooks/stripe` fulfillment.
- `GITHUB_TOKEN` — optional; lets the weekly growth-loop cron open GitHub issues for new-pair demand signals. Without it, detection still runs, issue filing is just skipped.

## Adding a new processor → accounting-software pair

1. Add `src/parsers/<processor>.ts` following the pattern in `stripe.ts`/`paypal.ts` (raw CSV → `NormalizedTransaction[]`).
2. If needed, add a new mapper in `src/mappers/`.
3. Wire it into `PARSERS` in `src/engine.ts`.
4. Add a fixture + tests.
5. Add an entry to `data/pairs.json` for its landing page.

This is also exactly what the weekly growth-loop issue template asks for — see `src/growth-loop.ts`.
