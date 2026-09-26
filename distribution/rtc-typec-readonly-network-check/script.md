# 50-Second Short — Verify RustChain With Three Read-Only Endpoints

**Hook:** “You can check whether RustChain is alive without an account or API key.”

The RustChain contributing guide gives three read-only commands:

`curl -sk https://rustchain.org/health`

`curl -sk https://rustchain.org/api/miners`

`curl -sk https://rustchain.org/epoch`

The health route tells you whether the node is responding. The miners route shows the current miner data. The epoch route shows current epoch state.

That makes a simple verification loop: health, miners, epoch.

No wallet write. No transaction. No signup.

If you want to verify the network state yourself, start with the same three endpoints the repository documents for contributors.

Source: Scottcjn/Rustchain CONTRIBUTING.md.
