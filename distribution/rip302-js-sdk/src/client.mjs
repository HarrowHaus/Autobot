// SPDX-License-Identifier: MIT

export class RustChainAgentEconomyError extends Error {
  constructor(message, { status = null, body = null, method = null, path = null } = {}) {
    super(message);
    this.name = 'RustChainAgentEconomyError';
    this.status = status;
    this.body = body;
    this.method = method;
    this.path = path;
  }
}

function requireText(value, name) {
  if (typeof value !== 'string' || !value.trim()) {
    throw new TypeError(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requirePositiveNumber(value, name) {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
    throw new TypeError(`${name} must be a finite number greater than zero`);
  }
  return value;
}

function cleanBaseUrl(value) {
  const url = new URL(requireText(value, 'baseUrl'));
  if (!['http:', 'https:'].includes(url.protocol)) {
    throw new TypeError('baseUrl must use http or https');
  }
  return url.toString().replace(/\/$/, '');
}

export class RustChainAgentEconomyClient {
  constructor({
    baseUrl = 'https://rustchain.org',
    wallet = null,
    timeoutMs = 15000,
    fetchImpl = globalThis.fetch,
  } = {}) {
    if (typeof fetchImpl !== 'function') {
      throw new TypeError('fetchImpl must be a function');
    }
    if (!Number.isInteger(timeoutMs) || timeoutMs <= 0) {
      throw new TypeError('timeoutMs must be a positive integer');
    }
    this.baseUrl = cleanBaseUrl(baseUrl);
    this.wallet = wallet == null ? null : requireText(wallet, 'wallet');
    this.timeoutMs = timeoutMs;
    this.fetchImpl = fetchImpl;
  }

  async _request(method, path, { query = null, body = null } = {}) {
    const url = new URL(this.baseUrl + path);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null && value !== '') {
          url.searchParams.set(key, String(value));
        }
      }
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let response;
    try {
      response = await this.fetchImpl(url, {
        method,
        headers: body == null ? undefined : { 'content-type': 'application/json' },
        body: body == null ? undefined : JSON.stringify(body),
        signal: controller.signal,
      });
    } catch (error) {
      const message = error?.name === 'AbortError'
        ? `request timed out after ${this.timeoutMs}ms`
        : `request failed: ${error?.message ?? String(error)}`;
      throw new RustChainAgentEconomyError(message, { method, path });
    } finally {
      clearTimeout(timer);
    }

    const text = await response.text();
    let parsed = null;
    if (text) {
      try {
        parsed = JSON.parse(text);
      } catch {
        parsed = text;
      }
    }

    if (!response.ok) {
      const detail = parsed && typeof parsed === 'object'
        ? parsed.error ?? parsed.message ?? JSON.stringify(parsed)
        : text || response.statusText;
      throw new RustChainAgentEconomyError(
        `${method} ${path} failed (${response.status}): ${detail}`,
        { status: response.status, body: parsed, method, path },
      );
    }
    return parsed;
  }

  _wallet(value) {
    return requireText(value ?? this.wallet, 'wallet');
  }

  browseJobs({ category = null, status = null, limit = null } = {}) {
    if (limit != null && (!Number.isInteger(limit) || limit <= 0)) {
      throw new TypeError('limit must be a positive integer');
    }
    return this._request('GET', '/agent/jobs', {
      query: { category, status, limit },
    });
  }

  getJob(jobId) {
    return this._request('GET', `/agent/jobs/${encodeURIComponent(requireText(jobId, 'jobId'))}`);
  }

  postJob({
    title,
    category,
    rewardRtc,
    description = '',
    tags = [],
    posterWallet = null,
  }) {
    if (!Array.isArray(tags) || tags.some((tag) => typeof tag !== 'string')) {
      throw new TypeError('tags must be an array of strings');
    }
    return this._request('POST', '/agent/jobs', {
      body: {
        poster_wallet: this._wallet(posterWallet),
        title: requireText(title, 'title'),
        category: requireText(category, 'category'),
        reward_rtc: requirePositiveNumber(rewardRtc, 'rewardRtc'),
        description: String(description ?? ''),
        tags,
      },
    });
  }

  claimJob(jobId, { workerWallet = null } = {}) {
    return this._jobAction(jobId, 'claim', {
      worker_wallet: this._wallet(workerWallet),
    });
  }

  deliverJob(jobId, {
    deliverableUrl,
    resultSummary = '',
    workerWallet = null,
  }) {
    return this._jobAction(jobId, 'deliver', {
      worker_wallet: this._wallet(workerWallet),
      deliverable_url: requireText(deliverableUrl, 'deliverableUrl'),
      result_summary: String(resultSummary ?? ''),
    });
  }

  acceptJob(jobId, { posterWallet = null, rating = null } = {}) {
    if (rating != null && (!Number.isInteger(rating) || rating < 1 || rating > 5)) {
      throw new TypeError('rating must be an integer from 1 to 5');
    }
    const body = { poster_wallet: this._wallet(posterWallet) };
    if (rating != null) body.rating = rating;
    return this._jobAction(jobId, 'accept', body);
  }

  disputeJob(jobId, { reason = '', posterWallet = null } = {}) {
    return this._jobAction(jobId, 'dispute', {
      poster_wallet: this._wallet(posterWallet),
      reason: String(reason ?? ''),
    });
  }

  cancelJob(jobId, { posterWallet = null } = {}) {
    return this._jobAction(jobId, 'cancel', {
      poster_wallet: this._wallet(posterWallet),
    });
  }

  _jobAction(jobId, action, body) {
    const id = encodeURIComponent(requireText(jobId, 'jobId'));
    return this._request('POST', `/agent/jobs/${id}/${action}`, { body });
  }

  getReputation(wallet = null) {
    return this._request(
      'GET',
      `/agent/reputation/${encodeURIComponent(this._wallet(wallet))}`,
    );
  }

  getStats() {
    return this._request('GET', '/agent/stats');
  }
}
