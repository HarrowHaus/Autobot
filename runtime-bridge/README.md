# A0 runtime bridge

This directory defines the durable handoff between SwarmBrain issue traffic and Vince's local A0 runtime.

Flow:
1. Issue #19 receives a task containing `Task ID:` and `Return nonce:`.
2. The inbox workflow stores an immutable JSON envelope under `runtime-bridge/inbox/`.
3. The local A0 runtime consumes the envelope and writes a receipt under `runtime-bridge/outbox/`.
4. The outbox workflow posts the receipt back to the issue.

The local receipt must distinguish A0 controller work, actually executed specialist work, and proposals. It must preserve task ID, nonce, artifact hash, provider/lease receipts and errors. No credential belongs in an envelope or receipt.

Economic fields are optional and descriptive. Internal contribution points and avoided cost are not cash. Confirmed external settlement must be recorded separately from contribution and savings.