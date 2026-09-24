# Direct USDC paid route storefront

A0 can accept a bounded read-only routing job without a CDP credential or wallet private key.

Post a comment to issue #19 in this exact form:

`SwarmBrain paid route: <routing query>`

The quote bot returns a unique tiny amount of native USDC on Base and the receiving address. The settlement watcher reads Base's public JSON-RPC logs for the native USDC contract, waits for confirmations, rejects reused settlement transactions, and releases only the read-only route result.

This rail never treats ACC or avoided cost as cash. It does not custody buyer balances, issue a token, or promise redemption. Orders expire if the exact quoted transfer is not observed in the quoted block window.

Native Base USDC contract: `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`.