# Script — ~45–55 seconds

Here’s a RustChain detail that is easy to get backwards: the vintage bonus does **not** keep growing forever.

In the current RIP-200 source, `DECAY_RATE_PER_YEAR` is **0.15**.

The code takes a hardware class’s base multiplier, separates out the bonus above 1.0, and reduces that bonus as chain age increases. The line is explicit: `aged_bonus = max(0, vintage_bonus * (1 - decay_rate * chain_age_years))`.

So when you see a G4 listed at 2.5× in the base table, that number is the starting hardware-class multiplier used by the model—not a promise that the bonus compounds upward forever.

Why do this? The source comment says the mechanism prevents vintage hardware from dominating indefinitely as the network ages.

That’s a much more interesting design than “older always means infinitely more.”
