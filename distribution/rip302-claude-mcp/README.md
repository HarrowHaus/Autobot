# RustChain RIP-302 Claude Code MCP Server

Dependency-free stdio MCP server for the RIP-302 Agent Economy, built for the open #685 Tier 2 Claude Code MCP integration bounty (75 RTC).

## Tools

- `rustchain_jobs_browse`
- `rustchain_job_get`
- `rustchain_job_post`
- `rustchain_job_claim`
- `rustchain_job_deliver`
- `rustchain_agent_reputation`
- `rustchain_agent_stats`

The server never stores or requests private keys. Write operations use only the configured public wallet identifier required by the RIP-302 API.

## Claude Code configuration

```json
{
  "mcpServers": {
    "rustchain-agent-economy": {
      "command": "node",
      "args": ["/absolute/path/to/server.js"],
      "env": {
        "RUSTCHAIN_NODE_URL": "https://50.28.86.131",
        "RUSTCHAIN_WALLET": "your-wallet"
      }
    }
  }
}
```

## Tests

```bash
node --test
```

Tests use injected fake HTTP. They do not post live jobs, claim work, or move RTC.
