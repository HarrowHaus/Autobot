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

const STYLE = `
  :root {
    color-scheme: light dark;
    --bg: #ffffff; --fg: #1a1a1a; --muted: #666; --border: #e2e2e2;
    --accent: #2563eb; --accent-fg: #ffffff; --card: #f7f7f8; --error: #b3261e; --ok: #16794f;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0f1115; --fg: #eaeaea; --muted: #9a9a9a; --border: #2a2d34; --card: #171a20; --accent: #5b8def; --accent-fg: #0f1115; }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--fg); font: 16px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
  main { max-width: 720px; margin: 0 auto; padding: 48px 20px 80px; }
  h1 { font-size: 1.6rem; margin-bottom: 4px; }
  .tagline { color: var(--muted); margin-top: 0; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 24px; margin-top: 24px; }
  label { display: block; font-weight: 600; margin: 16px 0 6px; font-size: 0.9rem; }
  select, input[type="email"] { width: 100%; padding: 10px 12px; border-radius: 8px; border: 1px solid var(--border); background: var(--bg); color: var(--fg); font-size: 1rem; }
  input[type="file"] { width: 100%; padding: 10px 0; }
  button { margin-top: 20px; width: 100%; padding: 12px 16px; border: none; border-radius: 8px; background: var(--accent); color: var(--accent-fg); font-size: 1rem; font-weight: 600; cursor: pointer; }
  button:disabled { opacity: 0.6; cursor: default; }
  .row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .privacy { font-size: 0.85rem; color: var(--muted); margin-top: 14px; }
  .result { margin-top: 20px; }
  .result a { display: inline-block; margin: 6px 12px 6px 0; padding: 8px 14px; border-radius: 8px; background: var(--accent); color: var(--accent-fg); text-decoration: none; font-weight: 600; font-size: 0.9rem; }
  .error { color: var(--error); font-weight: 600; }
  .ok { color: var(--ok); font-weight: 600; }
  .hidden { display: none; }
  ol { color: var(--fg); }
  footer { color: var(--muted); font-size: 0.85rem; margin-top: 40px; }
  footer a { color: inherit; }
`;

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
  return \`<a href="\${url}" download="\${file.filename}">Download \${file.filename}</a>\`;
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
        resultEl.innerHTML += \`<button id="buy-btn" type="button">Buy 10 credits — $15</button>\`;
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
      <p class="ok">Converted \${s.transactionCount} transaction(s) across \${s.payoutCount} payout(s).</p>
      <p>Gross \${centsToUsd(s.totalGrossCents)} &minus; Fees \${centsToUsd(s.totalFeeCents)} = Net \${centsToUsd(s.totalNetCents)}</p>
      <div>\${downloadLink(data.journalFile)}\${downloadLink(data.bankMatchFile)}</div>
      <p style="color:var(--muted);font-size:0.85rem;">Import the journal-entries file first, then the bank-match file when reconciling your bank feed.</p>
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
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>${pair.title} — PayoutSplit</title>
<meta name="description" content="${pair.metaDescription}">
<link rel="canonical" href="${BASE_URL}/convert/${pair.slug}">
<style>${STYLE}</style>
</head>
<body>
<main>
  <h1>${pair.title}</h1>
  <p class="tagline">${pair.painPoint}</p>

  <div class="card">
    <strong>How to get your ${pair.processorLabel} export</strong>
    <ol>
        ${steps}
    </ol>
  </div>

  <div class="card">
    <form id="convert-form">
      <input type="hidden" name="processor" value="${pair.processor}">
      <input type="hidden" name="target" value="${pair.target}">

      <label for="file">Your ${pair.processorLabel} export file (.csv)</label>
      <input type="file" id="file" name="file" accept=".csv" required>

      <label for="email">Email <span style="font-weight:400;color:var(--muted)">(only needed after your first free conversion)</span></label>
      <input type="email" id="email" name="email" placeholder="you@example.com">

      <button type="submit" id="submit-btn">Convert to ${pair.targetLabel}</button>
      <p class="privacy">Your file is processed in memory and never saved anywhere. Read the <a href="/privacy.html">privacy policy</a>.</p>
    </form>
    <div id="result" class="result hidden"></div>
  </div>

  <div class="card">
    <strong>Don't see your processor?</strong>
    <p style="color:var(--muted);margin-bottom:8px;">Tell us what you're trying to convert and we'll consider adding it.</p>
    <form id="feedback-form" style="display:flex;gap:8px;">
      <input type="text" id="feedback-query" placeholder="e.g. Square to Xero" style="flex:1;padding:10px 12px;border-radius:8px;border:1px solid var(--border);background:var(--bg);color:var(--fg);">
      <button type="submit" style="width:auto;margin-top:0;padding:10px 16px;">Send</button>
    </form>
    <p id="feedback-thanks" class="ok hidden">Thanks — noted.</p>
  </div>

  <footer>
    <a href="/">&larr; PayoutSplit home</a> &middot; <a href="/terms.html">Terms</a> &middot; <a href="/privacy.html">Privacy</a>
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
