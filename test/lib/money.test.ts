import { describe, expect, it } from "vitest";
import { centsToDecimalString, isSupportedCurrency, minorDigitsFor, parseStrictMoney } from "../../src/lib/money.js";

describe("parseStrictMoney — accepted shapes", () => {
  it("parses plain decimals", () => {
    expect(parseStrictMoney("100.00", "USD", "gross")).toEqual({ ok: true, cents: 10000 });
    expect(parseStrictMoney("1.5", "USD", "gross")).toEqual({ ok: true, cents: 150 });
    expect(parseStrictMoney("0", "USD", "gross")).toEqual({ ok: true, cents: 0 });
    expect(parseStrictMoney("0.00", "USD", "gross")).toEqual({ ok: true, cents: 0 });
  });

  it("parses negatives via leading minus", () => {
    expect(parseStrictMoney("-20.00", "USD", "fee")).toEqual({ ok: true, cents: -2000 });
    expect(parseStrictMoney("-1.75", "USD", "fee")).toEqual({ ok: true, cents: -175 });
  });

  it("parses accounting-style parenthetical negatives", () => {
    expect(parseStrictMoney("(20.00)", "USD", "fee")).toEqual({ ok: true, cents: -2000 });
  });

  it("parses zero-decimal currencies (e.g. JPY) with no fractional part", () => {
    expect(parseStrictMoney("100", "JPY", "gross")).toEqual({ ok: true, cents: 100 });
  });

  it("parses fewer fractional digits than the currency maximum (e.g. one digit for USD)", () => {
    expect(parseStrictMoney("1.5", "USD", "gross")).toEqual({ ok: true, cents: 150 });
  });
});

describe("parseStrictMoney — rejected shapes (never guesses)", () => {
  it("rejects an unsupported currency before even looking at the amount", () => {
    const result = parseStrictMoney("100.00", "XYZ", "gross");
    expect(result).toEqual({ ok: false, error: { code: "unsupported_currency", field: "gross", message: expect.any(String) } });
  });

  it("rejects missing/blank amounts rather than defaulting to zero", () => {
    expect(parseStrictMoney(undefined, "USD", "gross").ok).toBe(false);
    expect(parseStrictMoney(null, "USD", "gross").ok).toBe(false);
    expect(parseStrictMoney("", "USD", "gross")).toEqual({
      ok: false,
      error: { code: "blank_amount", field: "gross", message: expect.any(String) },
    });
  });

  it("rejects embedded whitespace", () => {
    const result = parseStrictMoney("100. 00", "USD", "gross");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("malformed_amount");
  });

  it("rejects more than one decimal point", () => {
    const result = parseStrictMoney("1.2.3", "USD", "gross");
    expect(result).toMatchObject({ ok: false, error: { code: "multiple_decimal_points" } });
  });

  it("rejects mixing parentheses and a minus sign", () => {
    const result = parseStrictMoney("(-20.00)", "USD", "gross");
    expect(result).toMatchObject({ ok: false, error: { code: "malformed_amount" } });
  });

  it("rejects thousands separators", () => {
    const result = parseStrictMoney("1,234.56", "USD", "gross");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("invalid_characters");
  });

  it("rejects currency symbols", () => {
    const result = parseStrictMoney("$100.00", "USD", "gross");
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.error.code).toBe("invalid_characters");
  });

  it("rejects more fractional precision than the currency supports", () => {
    const result = parseStrictMoney("100.123", "USD", "gross");
    expect(result).toMatchObject({ ok: false, error: { code: "excess_precision" } });
  });

  it("rejects a fractional part on a zero-decimal currency", () => {
    const result = parseStrictMoney("100.50", "JPY", "gross");
    expect(result.ok).toBe(false);
  });

  it("rejects values outside the safe integer range", () => {
    const result = parseStrictMoney("90071992547409929.00", "USD", "gross");
    expect(result).toMatchObject({ ok: false, error: { code: "unsafe_integer" } });
  });
});

describe("isSupportedCurrency / minorDigitsFor", () => {
  it("reports supported currencies and their minor-unit digit counts", () => {
    expect(isSupportedCurrency("USD")).toBe(true);
    expect(isSupportedCurrency("JPY")).toBe(true);
    expect(isSupportedCurrency("XYZ")).toBe(false);
    expect(minorDigitsFor("USD")).toBe(2);
    expect(minorDigitsFor("JPY")).toBe(0);
  });
});

describe("centsToDecimalString", () => {
  it("round-trips plain USD amounts", () => {
    expect(centsToDecimalString(10000, "USD")).toBe("100.00");
    expect(centsToDecimalString(-2000, "USD")).toBe("-20.00");
    expect(centsToDecimalString(5, "USD")).toBe("0.05");
    expect(centsToDecimalString(0, "USD")).toBe("0.00");
  });

  it("round-trips zero-decimal currencies without a decimal point", () => {
    expect(centsToDecimalString(100, "JPY")).toBe("100");
  });
});

describe("parseStrictMoney — fuzz: every accepted output round-trips through centsToDecimalString", () => {
  // Deterministic PRNG (mulberry32) so failures are reproducible without a
  // fuzzing dependency; not a substitute for the real property-based
  // fuzzers this table would eventually benefit from.
  function mulberry32(seed: number) {
    let a = seed;
    return () => {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  it("never throws and always agrees on sign + magnitude for 500 random well-formed amounts", () => {
    const rand = mulberry32(42);
    for (let i = 0; i < 500; i++) {
      const whole = Math.floor(rand() * 100000);
      const frac = Math.floor(rand() * 100)
        .toString()
        .padStart(2, "0");
      const negative = rand() < 0.5;
      const raw = `${negative ? "-" : ""}${whole}.${frac}`;

      const result = parseStrictMoney(raw, "USD", "amount");
      expect(result.ok).toBe(true);
      if (result.ok) {
        expect(centsToDecimalString(result.cents, "USD")).toBe(raw === "-0.00" ? "0.00" : raw);
      }
    }
  });

  it("never throws on arbitrary garbage strings", () => {
    const rand = mulberry32(7);
    const chars = "0123456789.,-()$ \t abcXYZ\n\"";
    for (let i = 0; i < 500; i++) {
      const len = Math.floor(rand() * 20);
      let raw = "";
      for (let j = 0; j < len; j++) raw += chars[Math.floor(rand() * chars.length)];
      expect(() => parseStrictMoney(raw, "USD", "amount")).not.toThrow();
    }
  });
});
