# Script — ~50–58 seconds

RustChain doesn’t identify a machine from one CPU-name string. Its Linux fingerprint module defines a sequence of physical-behavior checks.

The six core checks are:

one, clock-skew and oscillator drift;
two, cache timing;
three, SIMD unit identity;
four, thermal drift entropy;
five, instruction-path jitter;
and six, anti-emulation checks.

The code registers those checks together in `validate_all_checks()`.

The important point is not that any single measurement is magic. The protocol combines multiple independent hardware signals before using the fingerprint result.

For a real demonstration, run the project’s fingerprint script and capture **its actual output verbatim**. Don’t replace it with made-up PASS lines.

That’s the whole idea: measure the machine you actually have, then let the code report what it sees.
