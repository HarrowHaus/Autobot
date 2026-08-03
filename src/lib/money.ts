/**
 * All money is integer cents internally. Never floats — the whole product's
 * value proposition is that gross = fee + net down to the penny.
 */

/** Parses "1234.56", "-1234.56", "$1,234.56", "(1,234.56)" (accounting negatives) into integer cents. */
export function parseMoneyToCents(raw: string): number {
  const trimmed = raw.trim();
  if (trimmed === "") return 0;

  const isParenNegative = /^\(.*\)$/.test(trimmed);
  const cleaned = trimmed
    .replace(/[()]/g, "")
    .replace(/[$€£,]/g, "")
    .trim();

  const negative = isParenNegative || cleaned.startsWith("-");
  const abs = cleaned.replace(/^-/, "");

  const [wholePart = "", fracPart = ""] = abs.split(".");
  const whole = wholePart === "" ? 0 : parseInt(wholePart, 10);
  const frac = (fracPart + "00").slice(0, 2);
  const fracCents = frac === "" ? 0 : parseInt(frac, 10);

  if (Number.isNaN(whole) || Number.isNaN(fracCents)) {
    throw new Error(`Unparseable money value: "${raw}"`);
  }

  const cents = whole * 100 + fracCents;
  return negative ? -cents : cents;
}

export function centsToDecimalString(cents: number): string {
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const whole = Math.floor(abs / 100);
  const frac = abs % 100;
  return `${negative ? "-" : ""}${whole}.${frac.toString().padStart(2, "0")}`;
}
