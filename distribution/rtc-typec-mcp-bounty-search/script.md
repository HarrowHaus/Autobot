# 55-Second Short — Let an Agent Search RustChain Bounties

**Hook:** “RustChain’s MCP server has a read-only tool specifically for finding paid work.”

In `rustchain_mcp/server.py`, the `bounty_search` tool accepts a keyword, minimum and maximum RTC amount, difficulty, and repository selector.

The implementation searches open GitHub issues labeled `bounty`. It can search RustChain, BoTTube, or both, and returns matching issues with title, reward, difficulty, and URL.

The tool’s own docs also distinguish bounty accounting from market price: reward sizes use the project’s internal RTC reference rate, not an offered sale price.

So an MCP-capable agent can discover real open work programmatically instead of inventing demand.

Source: Scottcjn/rustchain-mcp.
