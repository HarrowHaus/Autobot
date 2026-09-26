# Storyboard

1. **0–7s — Hook**
   - Text: “RustChain vintage bonuses DECAY?”
   - No token-price graphics.

2. **7–20s — Constant**
   - Capture pinned source line 477:
     `DECAY_RATE_PER_YEAR = 0.15`.

3. **20–37s — Formula**
   - Capture lines around 509–510:
     - `vintage_bonus = base_multiplier - 1.0`
     - `aged_bonus = max(0, vintage_bonus * (1 - DECAY_RATE_PER_YEAR * chain_age_years))`

4. **37–48s — Base example**
   - Capture G4 entry at line 377 (`"g4": 2.5`).
   - Narration: “base hardware-class multiplier,” not guaranteed payout.

5. **48–55s — End**
   - Text: “Base multiplier ≠ forever-growing bonus.”
