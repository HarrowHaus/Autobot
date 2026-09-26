# Grazer to RustChain RIP-302 Marketplace Source

Focused implementation for #685 Tier 2 — Grazer skill for job marketplace browsing (75 RTC).

GrazerRIP302 is intentionally read-only. It queries the RIP-302 job board, filters by category/minimum RTC reward, and normalizes jobs into opportunity records that a Grazer discovery/ranking loop can combine with its other sources.

Tests use a fake HTTP opener and require no wallet, keys, or live network:

    python -m unittest discover -s tests -v
