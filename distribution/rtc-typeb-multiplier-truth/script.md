# RustChain's Antiquity Multiplier, Without the Hype

**Target length:** ~4:45  
**Source snapshot:** `Scottcjn/Rustchain@0906b21bd6d8c7c75c282df86adb2c5bcec88ff6`

## 0:00–0:25 — Hook
RustChain deliberately lets some old computers carry more reward weight than newer ones. But the real code is more specific than “old always wins.” A PowerPC G4 is 2.5x. Sandy Bridge is 1.1x. Generic modern Intel and AMD fallback classes are 0.8x. And the vintage bonus itself decays as the chain gets older.

## 0:25–1:10 — Read the multiplier table
Open `node/rip_200_round_robin_1cpu1vote.py`.

Current source:
- `g4` = 2.5x, line 377
- `powerpc g4` = 2.5x, line 378
- `g5` = 2.0x, line 382
- `sandy_bridge` = 1.1x, line 394
- `modern_intel` = 0.8x, line 409
- `modern_amd` = 0.8x, line 428
- `m1` = 1.2x, line 435

These are reward weights. They are not benchmark-speed claims and they are not proof-of-work difficulty targets.

## 1:10–1:55 — What incentive this creates
Most compute markets reward newer and faster machines. RustChain changes the incentive by assigning larger participation weight to some older verified hardware. That does not make a G4 faster than a modern CPU. It means the network chooses to reward that old physical machine more heavily.

The design goal is preservation: price hardware longevity and distinctness, not raw benchmark throughput.

## 1:55–2:45 — The important correction: the bonus decays
At line 477:

`DECAY_RATE_PER_YEAR = 0.15`

At line 510:

`aged_bonus = max(0, vintage_bonus * (1 - DECAY_RATE_PER_YEAR * chain_age_years))`

At line 512:

`return 1.0 + aged_bonus`

So the vintage *bonus* decays with chain age. It does not keep increasing because the computer gets another year older.

If a class starts at 2.5x, the part above the 1.0 baseline is 1.5. The code reduces that bonus over chain time until the extra vintage bonus can reach zero.

## 2:45–3:30 — Sandy Bridge vs modern x86
The current table gives `sandy_bridge` 1.1x while the generic `modern_intel` and `modern_amd` fallback classes are 0.8x.

That is enough to show the economic preference without inventing a benchmark, a fake “difficulty target,” or a made-up core penalty. The source already tells the story.

## 3:30–4:15 — Why operators and agents should care
Do not assume newer hardware automatically has better RustChain economics. When explaining a reward difference, use the source-controlled multiplier table and decay logic.

That makes the explanation auditable: exact class, exact multiplier, exact decay rule.

## 4:15–4:45 — Close
RustChain's antiquity model is not “old hardware magically becomes faster.”

It is a policy encoded in reward weights: some older verified hardware starts with a larger multiplier, modern fallback classes can start below 1.0, and the extra vintage bonus decays over chain time.

Verify the current source here:
https://github.com/Scottcjn/Rustchain
