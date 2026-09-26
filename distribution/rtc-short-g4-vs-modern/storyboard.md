# Storyboard / exact capture instructions

Format: vertical 9:16, <=60 seconds.

1. **0–6s — Hook**
   - On-screen text: “Why can a G4 get more RustChain weight than modern x86?”
   - Do not show a fake miner terminal.

2. **6–18s — Source capture**
   - Open the pinned RustChain source:
     https://github.com/Scottcjn/Rustchain/blob/91d0d2487743161e3dac7a8bd8116dd8f5f30678/node/rip_200_round_robin_1cpu1vote.py
   - Capture lines 371–384 showing the PowerPC table, including `"g4": 2.5`.
   - Zoom enough that the source line is readable.

3. **18–30s — Modern comparison**
   - Same pinned file.
   - Capture line 409 (`"modern_intel": 0.8`) and line 428 (`"modern_amd": 0.8`).

4. **30–43s — Live network**
   - In a terminal run:
     `curl -fsS https://rustchain.org/api/miners`
   - Capture whatever the endpoint returns **at recording time**. Do not pre-write expected values.
   - If G4/modern entries are visible, highlight them; otherwise just show that the live miner inventory is queryable.

5. **43–55s — Clarifier/end card**
   - Text: “Multiplier = protocol reward weight, not CPU speed.”
   - Link: https://github.com/Scottcjn/Rustchain
