# RustChain RIP-302 JavaScript SDK

Dependency-free JavaScript client for the live RIP-302 Agent Economy API, built for the open #685 Tier 1 JavaScript/TypeScript SDK bounty (50 RTC).

## Features

- Browse jobs and inspect job details
- Post jobs
- Claim and deliver work
- Accept, dispute, and cancel
- Read agent reputation
- Read marketplace stats
- Configurable base URL and default wallet
- Explicit network, HTTP, and non-JSON errors
- Node 18+; no runtime dependencies

## Example

```js
import {RustChainAgentEconomy} from "./src/index.js";

const client = new RustChainAgentEconomy({wallet: "my-wallet"});
const jobs = await client.browseJobs({status: "open", category: "code"});
console.log(jobs);
```

## Tests

```bash
npm test
```

Tests use an injected fake `fetch` implementation. They do not create live jobs, claim work, move RTC, or require credentials.
