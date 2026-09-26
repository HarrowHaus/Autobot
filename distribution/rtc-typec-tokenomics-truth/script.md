# 55-Second Short — The $0.15 RTC Number Is Not a Market Price

**Hook:** “If you see RTC listed at $0.15, here’s what the code actually says.”

RustChain exposes a read-only tokenomics endpoint. In `node/tokenomics_route.py`, total supply is fixed at **8,388,608 RTC**, or 2^23.

The same file contains holder milestones. At 1,000 holders the internal reference rate is **$0.15**, and at 2,000 holders the table lists **$0.20**.

But the API response labels that number an **internal reference rate for bounty accounting**, and explicitly says it is **not a market price or a promise of convertibility**.

So $0.15 is useful for sizing bounties. It is not proof that one RTC can currently be sold for fifteen cents.

Source: Scottcjn/Rustchain, `node/tokenomics_route.py`.
