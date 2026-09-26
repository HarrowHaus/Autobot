# Script — ~45–55 seconds

RustChain’s RIP-200 file says it directly: **“1 CPU = 1 Vote.”**

That is a very different idea from buying more hashrate and dominating a proof-of-work race.

The round-robin selection code describes the system as deterministic rather than a lottery. Then reward weighting can reflect the machine’s verified hardware class and antiquity multiplier.

The same source includes a reference reward-distribution example using **1.5 RTC total**, and the live `/epoch` endpoint reports the current epoch pot and enrolled-miner count.

So the clean mental model is: physical machines attest, enrolled CPUs participate, and reward share is distributed by the protocol’s weighting rules—not by who can brute-force the most hashes.

If you want the current numbers, don’t trust this video. Query `rustchain.org/epoch` yourself.
