# Storyboard

Vertical 9:16, <=60s.

1. **0–8s**
   - Open pinned `miners/linux/fingerprint_checks.py`.
   - Capture header lines 9–14 listing the six checks.

2. **8–35s**
   - Scroll/cut through the registration list at lines 611–616:
     - clock_drift
     - cache_timing
     - simd_identity
     - thermal_drift
     - instruction_jitter
     - anti_emulation

3. **35–50s — Real terminal capture**
   - From a real RustChain checkout:
     `python3 miners/linux/fingerprint_checks.py`
   - Record the program’s actual output.
   - Do not reformat a mock as a capture.
   - If the installed ROM database causes an additional ROM check, keep it; explain that the six listed here are the core checks.

4. **50–58s**
   - End card: “Multiple signals. One physical machine.”
