export class RustChainAgentEconomyError extends Error {
  constructor(message, {status = null, body = null} = {}) {
    super(message);
    this.name = "RustChainAgentEconomyError";
    this.status = status;
    this.body = body;
  }
}

export class RustChainAgentEconomy {
  constructor({baseUrl = "https://50.28.86.131", wallet = null, fetchImpl = globalThis.fetch} = {}) {
    if (!fetchImpl) throw new Error("fetch implementation required");
    this.baseUrl = baseUrl.replace(/\/$/, "");
    this.wallet = wallet;
    this.fetch = fetchImpl;
  }

  async request(method, path, body = undefined, query = undefined) {
    const url = new URL(this.baseUrl + path);
    if (query) {
      for (const [key, value] of Object.entries(query)) {
        if (value !== undefined && value !== null && value !== "") url.searchParams.set(key, String(value));
      }
    }
    const opts = {method, headers: {accept: "application/json"}};
    if (body !== undefined) {
      opts.headers["content-type"] = "application/json";
      opts.body = JSON.stringify(body);
    }
    let resp;
    try {
      resp = await this.fetch(url, opts);
    } catch (err) {
      throw new RustChainAgentEconomyError(`network error: ${err.message}`);
    }
    const text = await resp.text();
    let data = null;
    if (text) {
      try { data = JSON.parse(text); }
      catch {
        throw new RustChainAgentEconomyError("non-JSON response", {status: resp.status, body: text.slice(0, 500)});
      }
    }
    if (!resp.ok) {
      const msg = data?.error || data?.message || `HTTP ${resp.status}`;
      throw new RustChainAgentEconomyError(msg, {status: resp.status, body: data});
    }
    return data;
  }

  browseJobs({status = "open", category, limit} = {}) {
    return this.request("GET", "/agent/jobs", undefined, {status, category, limit});
  }

  getJob(jobId) {
    return this.request("GET", `/agent/jobs/${encodeURIComponent(jobId)}`);
  }

  postJob({title, category, rewardRtc, description = "", tags = [], posterWallet = this.wallet}) {
    if (!posterWallet) throw new Error("poster wallet required");
    return this.request("POST", "/agent/jobs", {
      poster_wallet: posterWallet,
      title,
      category,
      reward_rtc: rewardRtc,
      description,
      tags,
    });
  }

  claimJob(jobId, workerWallet = this.wallet) {
    if (!workerWallet) throw new Error("worker wallet required");
    return this.request("POST", `/agent/jobs/${encodeURIComponent(jobId)}/claim`, {worker_wallet: workerWallet});
  }

  deliverJob(jobId, {deliverableUrl, resultSummary = "", workerWallet = this.wallet}) {
    if (!workerWallet) throw new Error("worker wallet required");
    return this.request("POST", `/agent/jobs/${encodeURIComponent(jobId)}/deliver`, {
      worker_wallet: workerWallet,
      deliverable_url: deliverableUrl,
      result_summary: resultSummary,
    });
  }

  acceptJob(jobId, {posterWallet = this.wallet, rating, feedback} = {}) {
    if (!posterWallet) throw new Error("poster wallet required");
    const body = {poster_wallet: posterWallet};
    if (rating !== undefined) body.rating = rating;
    if (feedback !== undefined) body.feedback = feedback;
    return this.request("POST", `/agent/jobs/${encodeURIComponent(jobId)}/accept`, body);
  }

  disputeJob(jobId, {posterWallet = this.wallet, reason = ""} = {}) {
    if (!posterWallet) throw new Error("poster wallet required");
    return this.request("POST", `/agent/jobs/${encodeURIComponent(jobId)}/dispute`, {
      poster_wallet: posterWallet,
      reason,
    });
  }

  cancelJob(jobId, posterWallet = this.wallet) {
    if (!posterWallet) throw new Error("poster wallet required");
    return this.request("POST", `/agent/jobs/${encodeURIComponent(jobId)}/cancel`, {poster_wallet: posterWallet});
  }

  reputation(wallet = this.wallet) {
    if (!wallet) throw new Error("wallet required");
    return this.request("GET", `/agent/reputation/${encodeURIComponent(wallet)}`);
  }

  stats() {
    return this.request("GET", "/agent/stats");
  }
}

export default RustChainAgentEconomy;
