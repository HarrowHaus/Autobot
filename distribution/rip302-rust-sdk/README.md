# RustChain RIP-302 Rust SDK

A synchronous Rust client for the RIP-302 Agent Economy API, built for the open **#685 Tier 1 Rust client crate (50 RTC)**.

## Coverage

- Browse jobs
- Get job details
- Post jobs
- Claim work
- Deliver results
- Accept/dispute/cancel
- Reputation
- Marketplace stats
- Typed API/network errors
- Configurable default wallet

Tests use a local HTTP server only. They do not post live jobs or move RTC.

Run:

    cargo test

Example:

    use rustchain_agent_economy::AgentEconomyClient;
    let client = AgentEconomyClient::new("https://50.28.86.131", Some("my-wallet".into()));
    let jobs = client.browse_jobs(Some("open"), None)?;
