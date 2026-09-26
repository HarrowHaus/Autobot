use reqwest::blocking::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AgentEconomyError {
    #[error("wallet is required")]
    WalletRequired,
    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),
    #[error("api error ({status}): {message}")]
    Api { status: u16, message: String, body: Option<Value> },
}

#[derive(Debug, Clone)]
pub struct AgentEconomyClient {
    base_url: String,
    wallet: Option<String>,
    http: Client,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PostJob {
    pub title: String,
    pub category: String,
    pub reward_rtc: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
}

impl AgentEconomyClient {
    pub fn new(base_url: impl Into<String>, wallet: Option<String>) -> Self {
        Self {
            base_url: base_url.into().trim_end_matches('/').to_string(),
            wallet,
            http: Client::new(),
        }
    }

    fn wallet<'a>(&'a self, override_wallet: Option<&'a str>) -> Result<&'a str, AgentEconomyError> {
        override_wallet
            .or(self.wallet.as_deref())
            .filter(|v| !v.trim().is_empty())
            .ok_or(AgentEconomyError::WalletRequired)
    }

    fn decode(&self, response: reqwest::blocking::Response) -> Result<Value, AgentEconomyError> {
        let status = response.status();
        let text = response.text()?;
        let body = if text.trim().is_empty() { None } else { serde_json::from_str(&text).ok() };
        if !status.is_success() {
            let message = body.as_ref()
                .and_then(|v| v.get("error"))
                .and_then(Value::as_str)
                .unwrap_or("request failed")
                .to_string();
            return Err(AgentEconomyError::Api { status: status.as_u16(), message, body });
        }
        Ok(body.unwrap_or(Value::Null))
    }

    pub fn browse_jobs(&self, status: Option<&str>, category: Option<&str>) -> Result<Value, AgentEconomyError> {
        let mut req = self.http.get(format!("{}/agent/jobs", self.base_url));
        if let Some(v) = status { req = req.query(&[("status", v)]); }
        if let Some(v) = category { req = req.query(&[("category", v)]); }
        self.decode(req.send()?)
    }

    pub fn get_job(&self, job_id: &str) -> Result<Value, AgentEconomyError> {
        self.decode(self.http.get(format!("{}/agent/jobs/{}", self.base_url, job_id)).send()?)
    }

    pub fn marketplace_stats(&self) -> Result<Value, AgentEconomyError> {
        self.decode(self.http.get(format!("{}/agent/stats", self.base_url)).send()?)
    }

    pub fn reputation(&self, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        let wallet = self.wallet(wallet)?;
        self.decode(self.http.get(format!("{}/agent/reputation/{}", self.base_url, wallet)).send()?)
    }

    pub fn post_job(&self, job: &PostJob, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        let mut payload = serde_json::to_value(job).expect("PostJob serialization cannot fail");
        payload["poster_wallet"] = Value::String(self.wallet(wallet)?.to_string());
        self.decode(self.http.post(format!("{}/agent/jobs", self.base_url)).json(&payload).send()?)
    }

    pub fn claim_job(&self, job_id: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        self.post_wallet_action(job_id, "claim", "worker_wallet", wallet)
    }

    pub fn accept_delivery(&self, job_id: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        self.post_wallet_action(job_id, "accept", "poster_wallet", wallet)
    }

    pub fn cancel_job(&self, job_id: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        self.post_wallet_action(job_id, "cancel", "poster_wallet", wallet)
    }

    fn post_wallet_action(&self, job_id: &str, action: &str, key: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        let mut payload = serde_json::Map::new();
        payload.insert(key.to_string(), Value::String(self.wallet(wallet)?.to_string()));
        self.decode(self.http
            .post(format!("{}/agent/jobs/{}/{}", self.base_url, job_id, action))
            .json(&Value::Object(payload))
            .send()?)
    }

    pub fn deliver_job(&self, job_id: &str, deliverable_url: &str, result_summary: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        let payload = serde_json::json!({
            "worker_wallet": self.wallet(wallet)?,
            "deliverable_url": deliverable_url,
            "result_summary": result_summary,
        });
        self.decode(self.http.post(format!("{}/agent/jobs/{}/deliver", self.base_url, job_id)).json(&payload).send()?)
    }

    pub fn dispute_delivery(&self, job_id: &str, reason: &str, wallet: Option<&str>) -> Result<Value, AgentEconomyError> {
        let payload = serde_json::json!({
            "poster_wallet": self.wallet(wallet)?,
            "reason": reason,
        });
        self.decode(self.http.post(format!("{}/agent/jobs/{}/dispute", self.base_url, job_id)).json(&payload).send()?)
    }
}
