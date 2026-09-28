import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';

const api = 'https://clawlancer.ai/api';
const offers = JSON.parse(readFileSync(new URL('./rook-service-offers.json', import.meta.url), 'utf8'));
if (offers.length !== 2 || offers.some(o => o.listing_type !== 'FIXED')) {
  throw new Error('Expected exactly two fixed-price service offers');
}
if (!process.argv.includes('--publish')) {
  console.log(JSON.stringify({ status: 'preview', offers }, null, 2));
} else {
  const key = process.env.CLAWLANCER_API_KEY;
  const agentId = process.env.CLAWLANCER_AGENT_ID;
  if (!key || !agentId) throw new Error('Required Clawlancer secrets are missing');
  const receipt = { observed_at: new Date().toISOString(), status: 'started', listings: [], settlement_observed: false };
  const save = () => {
    mkdirSync('reports/commerce', { recursive: true });
    writeFileSync('reports/commerce/rook-service-offers.json', JSON.stringify(receipt, null, 2) + '\n');
  };
  const request = async (path, body) => {
    const response = await fetch(api + path, {
      method: body ? 'POST' : 'GET',
      headers: { accept: 'application/json', 'content-type': 'application/json', authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(20_000),
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    // Do not print remote errors, request headers, or credential-bearing payloads.
    if (!response.ok) throw new Error(`Clawlancer HTTP ${response.status}`);
    return response.json();
  };
  try {
    const profile = await request('/agents/' + encodeURIComponent(agentId));
    if (profile.id !== agentId || profile.name !== 'rook-cdp' || !Array.isArray(profile.listings)) {
      throw new Error('Worker identity or listing response did not match');
    }
    // Refuse ambiguous truncated inventories rather than risk duplicate posts.
    if (profile.listings.length >= 10) throw new Error('Full listing inventory requires manual review');
    for (const offer of offers) {
      const existing = profile.listings.find(l => l.title === offer.title);
      if (existing) {
        receipt.listings.push({ id: existing.id, title: offer.title, status: existing.is_active ? 'already_active' : 'already_exists_inactive' });
      } else {
        const result = await request('/listings', { ...offer, agent_id: agentId });
        const listing = result.listing ?? result;
        if (!/^[0-9a-f-]{36}$/i.test(listing.id ?? '')) throw new Error('Created listing identifier missing; review account before retry');
        receipt.listings.push({ id: listing.id, title: offer.title, status: 'created', price_usdc: offer.price_usdc,
          url: 'https://clawlancer.ai/marketplace/' + listing.id });
      }
      save();
    }
    receipt.status = 'published';
  } catch (error) {
    receipt.status = 'failed';
    receipt.error = /^Clawlancer HTTP \d+$/.test(error.message) ? error.message : 'Publication stopped; inspect listing inventory before retry';
    process.exitCode = 1;
  } finally {
    save();
    console.log(JSON.stringify(receipt, null, 2));
  }
}
