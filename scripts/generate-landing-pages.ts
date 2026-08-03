import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

interface Pair {
  slug: string;
  processor: string;
  processorLabel: string;
  target: string;
  targetLabel: string;
  title: string;
  metaDescription: string;
  painPoint: string;
  howToExport: string[];
}

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const BASE_URL = process.env.SITE_BASE_URL || "https://payoutsplit.io";

const pairs: Pair[] = JSON.parse(readFileSync(path.join(ROOT, "data/pairs.json"), "utf-8"));

interface LedgerRow {
  label: string;
  amount: string;
}

// Real numbers, taken from the test fixtures, so the example is honest rather than made up.
const COMPARE_EXAMPLES: Record<string, { before: LedgerRow; after: LedgerRow[] }> = {
  stripe: {
    before: { label: "STRIPE PAYOUT", amount: "+$1,255.63" },
    after: [
      { label: "Undeposited Funds", amount: "Dr 1,255.63" },
      { label: "Merchant Processing Fees", amount: "Dr 43.70" },
      { label: "Sales Income", amount: "Cr 1,299.33" },
    ],
  },
  paypal: {
    before: { label: "PAYPAL TRANSACTION", amount: "+$96.80" },
    after: [
      { label: "Undeposited Funds", amount: "Dr 96.80" },
      { label: "Merchant Processing Fees", amount: "Dr 3.20" },
      { label: "Sales Income", amount: "Cr 100.00" },
    ],
  },
};

function ledgerRow(row: LedgerRow): string {
  return `<div class="ledger-row mono"><span>${row.label}</span><span class="amount">${row.amount}</span></div>`;
}

const SCRIPT = `
const form = document.getElementById('convert-form');
const resultEl = document.getElementById('result');
const submitBtn = document.getElementById('submit-btn');

function centsToUsd(cents) {
  return (cents / 100).toLocaleString('en-US', { style: 'currency', currency: 'USD' });
}
function downloadLink(file) {
  const blob = new Blob([file.content], { type: file.mimeType });
  const url = URL.createObjectURL(blob);
  return \`<a class="file-link" href="\${url}" download="\${file.filename}">Download \${file.filename}</a>\`;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  submitBtn.disabled = true;
  submitBtn.textContent = 'Converting…';
  resultEl.classList.remove('hidden');
  resultEl.innerHTML = '';

  const fd = new FormData(form);
  try {
    const res = await fetch('/convert', { method: 'POST', body: fd });
    const data = await res.json();

    if (res.status === 402) {
      resultEl.innerHTML = \`<p class="error">\${data.error === 'email_required_after_trial' ? 'Enter your email to continue after your free conversion.' : 'Free conversion used. Buy credits to continue.'}</p>\`;
      if (data.error === 'no_credits') {
        resultEl.innerHTML += \`<button id="buy-btn" type="button" class="btn">Buy 10 credits — $15</button>\`;
        document.getElementById('buy-btn').addEventListener('click', async () => {
          const email = document.getElementById('email').value;
          const checkoutRes = await fetch('/billing/checkout', {
            method: 'POST', headers: { 'content-type': 'application/json' },
            body: JSON.stringify({ pack: 'web_10', email }),
          });
          const checkout = await checkoutRes.json();
          if (checkout.url) window.location.href = checkout.url;
          else resultEl.innerHTML += '<p class="error">Billing isn\\'t live yet — check back soon.</p>';
        });
      }
      return;
    }
    if (!data.ok) {
      resultEl.innerHTML = \`<p class="error">\${data.message || data.error}</p>\`;
      return;
    }
    const s = data.summary;
    resultEl.innerHTML = \`
      <p class="ok-text">Converted \${s.transactionCount} transaction(s) across \${s.payoutCount} payout(s).</p>
      <p>Gross \${centsToUsd(s.totalGrossCents)} &minus; Fees \${centsToUsd(s.totalFeeCents)} = Net \${centsToUsd(s.totalNetCents)}</p>
      <div>\${downloadLink(data.journalFile)}\${downloadLink(data.bankMatchFile)}</div>
      <p class="fine-print">Import the journal-entries file first, then the bank-match file when reconciling your bank feed.</p>
    \`;
  } catch (err) {
    resultEl.innerHTML = \`<p class="error">Something went wrong: \${err}</p>\`;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Convert';
  }
});

document.getElementById('feedback-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const query = document.getElementById('feedback-query').value.trim();
  if (!query) return;
  await fetch('/feedback/missing-platform', {
    method: 'POST', headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ query }),
  });
  document.getElementById('feedback-query').value = '';
  document.getElementById('feedback-thanks').classList.remove('hidden');
});
`;

function renderPage(pair: Pair): string {
  const steps = pair.howToExport.map((s) => `<li>${s}</li>`).join("\n        ");
  const example = COMPARE_EXAMPLES[pair.processor] ?? COMPARE_EXAMPLES.stripe!;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${pair.title} — PayoutSplit</title>
<meta name="description" content="${pair.metaDescription}">
<link rel="canonical" href="${BASE_URL}/convert/${pair.slug}">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<main>

<section>
  <span class="eyebrow">${pair.processorLabel} → ${pair.targetLabel}</span>
  <h1>${pair.title}</h1>
  <p class="tagline">${pair.painPoint}</p>

  <div class="compare">
    <div class="compare-panel before">
      <span class="panel-label">Your bank feed</span>
      ${ledgerRow(example.before)}
    </div>
    <div class="arrow" aria-hidden="true">→</div>
    <div class="compare-panel after">
      <span class="panel-label">What PayoutSplit gives you</span>
      ${example.after.map(ledgerRow).join("\n      ")}
    </div>
  </div>

  <a href="#convert" class="btn hero-cta">Convert your first file free</a>
</section>

<section>
  <p class="section-label">How to get your ${pair.processorLabel} export</p>
  <div class="card">
    <ol>
        ${steps}
    </ol>
  </div>
</section>

<section id="convert">
  <p class="section-label">Convert a file</p>
  <div class="card">
    <form id="convert-form">
      <input type="hidden" name="processor" value="${pair.processor}">
      <input type="hidden" name="target" value="${pair.target}">

      <label for="file">Your ${pair.processorLabel} export file (.csv)</label>
      <input type="file" id="file" name="file" accept=".csv" required>

      <label for="email">Email <span style="font-weight:400;color:var(--muted)">(only needed after your first free conversion)</span></label>
      <input type="email" id="email" name="email" placeholder="you@example.com">

      <button type="submit" id="submit-btn" class="btn-block">Convert to ${pair.targetLabel}</button>
    </form>

    <p class="trust-line"><strong>Nothing is ever stored.</strong> Your file is processed in memory and discarded immediately. Read the <a href="/privacy.html">privacy policy</a>.</p>

    <div id="result" class="result hidden"></div>
  </div>
</section>

<section>
  <p class="section-label">Pricing</p>
  <div class="pricing-grid">
    <div class="price-tile"><div class="amount">Free</div><div class="desc">1st conversion</div></div>
    <div class="price-tile"><div class="amount">$2</div><div class="desc">per conversion</div></div>
    <div class="price-tile"><div class="amount">$15</div><div class="desc">10-pack</div></div>
    <div class="price-tile"><div class="amount">$60</div><div class="desc">50-pack</div></div>
  </div>
  <p class="fine-print">No subscription, no account required to start. Credits never expire.</p>
</section>

<section>
  <p class="section-label">Don't see your processor?</p>
  <form id="feedback-form" class="inline-form">
    <input type="text" id="feedback-query" placeholder="e.g. Square to Xero">
    <button type="submit" class="btn-secondary">Send</button>
  </form>
  <p id="feedback-thanks" class="ok-text hidden fine-print">Thanks — noted.</p>
</section>

<footer>
  <a href="/">&larr; PayoutSplit home</a> &middot; <a href="https://github.com/harrowhaus/autobot">Open source</a> &middot; <a href="/terms.html">Terms</a> &middot; <a href="/privacy.html">Privacy</a>
</footer>

</main>
<script>${SCRIPT}</script>
</body>
</html>
`;
}

function renderSitemap(pairs: Pair[]): string {
  const staticUrls = ["/", "/terms.html", "/privacy.html"];
  const pairUrls = pairs.map((p) => `/convert/${p.slug}`);
  const urls = [...staticUrls, ...pairUrls];
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${urls.map((u) => `  <url><loc>${BASE_URL}${u}</loc></url>`).join("\n")}
</urlset>
`;
}

const outDir = path.join(ROOT, "public/convert");
if (!existsSync(outDir)) mkdirSync(outDir, { recursive: true });

for (const pair of pairs) {
  writeFileSync(path.join(outDir, `${pair.slug}.html`), renderPage(pair));
}
writeFileSync(path.join(ROOT, "public/sitemap.xml"), renderSitemap(pairs));

console.log(`Generated ${pairs.length} landing pages + sitemap.xml`);
