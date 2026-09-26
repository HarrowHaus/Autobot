import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';

import {
  RustChainAgentEconomyClient,
  RustChainAgentEconomyError,
} from '../src/client.mjs';

async function withServer(handler, fn) {
  const server = http.createServer(handler);
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  try {
    await fn(`http://127.0.0.1:${port}`);
  } finally {
    await new Promise((resolve, reject) =>
      server.close((error) => error ? reject(error) : resolve()),
    );
  }
}

async function readJson(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
}

test('browse, detail, reputation and stats use the documented GET routes', async () => {
  const seen = [];
  await withServer((req, res) => {
    seen.push(req.url);
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ ok: true, path: req.url }));
  }, async (baseUrl) => {
    const client = new RustChainAgentEconomyClient({ baseUrl, wallet: 'alice' });
    await client.browseJobs({ category: 'code', limit: 7 });
    await client.getJob('job abc');
    await client.getReputation();
    await client.getStats();
  });
  assert.deepEqual(seen, [
    '/agent/jobs?category=code&limit=7',
    '/agent/jobs/job%20abc',
    '/agent/reputation/alice',
    '/agent/stats',
  ]);
});

test('postJob maps JavaScript names to the RIP-302 request shape', async () => {
  await withServer(async (req, res) => {
    assert.equal(req.method, 'POST');
    assert.equal(req.url, '/agent/jobs');
    assert.deepEqual(await readJson(req), {
      poster_wallet: 'alice',
      title: 'Write docs',
      category: 'writing',
      reward_rtc: 2.5,
      description: 'Source-backed guide',
      tags: ['docs', 'rip302'],
    });
    res.setHeader('content-type', 'application/json');
    res.end('{"ok":true,"job_id":"job_1"}');
  }, async (baseUrl) => {
    const client = new RustChainAgentEconomyClient({ baseUrl, wallet: 'alice' });
    const result = await client.postJob({
      title: 'Write docs',
      category: 'writing',
      rewardRtc: 2.5,
      description: 'Source-backed guide',
      tags: ['docs', 'rip302'],
    });
    assert.equal(result.job_id, 'job_1');
  });
});

test('claim, deliver, accept, dispute and cancel map to lifecycle endpoints', async () => {
  const calls = [];
  await withServer(async (req, res) => {
    calls.push({ method: req.method, url: req.url, body: await readJson(req) });
    res.setHeader('content-type', 'application/json');
    res.end('{"ok":true}');
  }, async (baseUrl) => {
    const client = new RustChainAgentEconomyClient({ baseUrl, wallet: 'agent-a' });
    await client.claimJob('job1');
    await client.deliverJob('job1', {
      deliverableUrl: 'https://example.test/work',
      resultSummary: 'done',
    });
    await client.acceptJob('job1', { rating: 5 });
    await client.disputeJob('job1', { reason: 'needs changes' });
    await client.cancelJob('job1');
  });
  assert.deepEqual(calls.map((x) => x.url), [
    '/agent/jobs/job1/claim',
    '/agent/jobs/job1/deliver',
    '/agent/jobs/job1/accept',
    '/agent/jobs/job1/dispute',
    '/agent/jobs/job1/cancel',
  ]);
  assert.equal(calls[0].body.worker_wallet, 'agent-a');
  assert.equal(calls[1].body.deliverable_url, 'https://example.test/work');
  assert.equal(calls[2].body.rating, 5);
  assert.equal(calls[3].body.reason, 'needs changes');
  assert.equal(calls[4].body.poster_wallet, 'agent-a');
});

test('HTTP errors become structured RustChainAgentEconomyError instances', async () => {
  await withServer((_req, res) => {
    res.statusCode = 409;
    res.setHeader('content-type', 'application/json');
    res.end(JSON.stringify({ error: 'job_already_claimed' }));
  }, async (baseUrl) => {
    const client = new RustChainAgentEconomyClient({ baseUrl, wallet: 'alice' });
    await assert.rejects(
      () => client.claimJob('job1'),
      (error) => {
        assert.ok(error instanceof RustChainAgentEconomyError);
        assert.equal(error.status, 409);
        assert.equal(error.body.error, 'job_already_claimed');
        return true;
      },
    );
  });
});

test('invalid local inputs fail before network access', async () => {
  let called = false;
  const client = new RustChainAgentEconomyClient({
    wallet: 'alice',
    fetchImpl: async () => {
      called = true;
      throw new Error('should not run');
    },
  });
  assert.throws(() => client.browseJobs({ limit: 0 }), /positive integer/);
  assert.throws(
    () => client.postJob({ title: '', category: 'code', rewardRtc: 1 }),
    /title/,
  );
  assert.throws(
    () => client.acceptJob('job', { rating: 6 }),
    /rating/,
  );
  assert.equal(called, false);
});
