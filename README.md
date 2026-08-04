# PayoutSplit (alpha)

**Status: early alpha. Not production accounting software. Not tested against a real Stripe export.**

Reads a Stripe **Payout Reconciliation Itemized** CSV export and produces a
*reconciliation report*: per-payout activity broken out by reporting
category, with the file's stated net compared against an independently
recalculated net.

It deliberately does **not**:

- produce a QuickBooks or Xero import file (the QuickBooks journal builder
  exists and is tested, but is gated off behind `ALLOW_QBO_EXPORT` until its
  output has actually been imported into a real QuickBooks sandbox);
- support PayPal, Square, or any processor other than Stripe;
- accept payment — there is no billing, account, or API-key system in this
  codebase at all;
- guess. Anything it cannot interpret against the one documented schema it
  supports is reported as an error rather than silently absorbed.

## Why it fails loudly

This tool handles money, so it is built to fail closed. Unknown reporting
categories, mixed currencies, malformed amounts, duplicate transaction IDs,
and rows whose `gross`/`fee`/`net` don't satisfy Stripe's documented
arithmetic identity are all **blocking errors**, not warnings. A file that
produces no output is a better outcome than a report that quietly
misclassifies a transaction.

Rows that are merely out of scope (for example, balance transactions not yet
associated with an automatic payout) are excluded rather than blocking — but
every exclusion is recorded in the report's row audit with its reason. No row
is ever silently dropped.

## Known limitations

See the "Remaining unsupported cases" section of the open containment PR for
the current list. The most important ones:

- **The validator has never been run against a real, unmodified Stripe
  export.** All fixtures are synthetic, built from documented schemas.
- The `reporting_category` allowlist is assembled from Stripe's published
  documentation, but Stripe does not publish one authoritative machine-readable
  enum. Categories whose accounting treatment isn't documented are recognized
  but deliberately left unclassified rather than guessed at.
- Payout **completeness cannot be verified** from an itemized export alone —
  the report says so explicitly rather than implying the totals are whole.

## Architecture

Single Cloudflare Worker (Hono). Uploaded CSVs are parsed and validated
entirely in memory for the duration of one request — file content is never
written to disk, R2, or a database.

```
src/validators/stripe-payout-itemized.ts   the strict single-format validator
src/lib/money.ts                           strict integer-minor-unit money parsing
src/lib/qbo-journal-builder.ts             QuickBooks journal (gated off)
src/engine.ts                              orchestration
src/index.ts                               Hono routes: /convert, /feedback/*, /healthz
```

D1 stores only anonymous usage metadata (`conversions`) and "didn't see your
processor" submissions (`landing_page_queries`). KV stores only short-lived
rate-limit counters. See [`public/privacy.html`](public/privacy.html).

## Local development

```
npm install
npm run dev          # wrangler dev
npm test             # vitest
npm run typecheck
npm run db:migrate:local
```

## Deployment

Deploys via Cloudflare's Git integration ("Workers Builds") on push to `main`.
GitHub Actions (`.github/workflows/test.yml`) only runs tests and typecheck;
it does not deploy.

**PR branches must not be deployed to the production Worker.**

No secrets are required — there are none to set. Both `BILLING_ENABLED` and
`ALLOW_QBO_EXPORT` are `"false"` in `wrangler.toml` and must stay that way
until the manual validation checklist in the containment PR is done.

## License

See [LICENSE](LICENSE). The source is published for inspection — so that
anyone considering uploading financial data can read exactly what happens to
it — under a permissive license.
