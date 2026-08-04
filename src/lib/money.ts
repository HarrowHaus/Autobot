/**
 * Strict money parsing. All money is integer minor-units (cents for USD)
 * internally, computed only from validated, unambiguous input — this
 * module never guesses at locale/thousands-separator conventions and never
 * silently absorbs an unexpected currency symbol.
 *
 * Money never throws: every failure is a structured ValidationError so
 * callers can report exactly what was wrong with which field, in which row.
 */

export interface ValidationError {
  code: string;
  field: string;
  message: string;
}

export type MoneyResult = { ok: true; cents: number } | { ok: false; error: ValidationError };

function err(code: string, field: string, message: string): MoneyResult {
  return { ok: false, error: { code, field, message } };
}

// Minor-unit (decimal) digit counts we explicitly support. A currency not
// listed here is rejected outright rather than assumed to behave like USD.
const CURRENCY_MINOR_DIGITS: Record<string, number> = {
  USD: 2,
  EUR: 2,
  GBP: 2,
  CAD: 2,
  AUD: 2,
  NZD: 2,
  CHF: 2,
  JPY: 0,
  KRW: 0,
};

export function isSupportedCurrency(code: string): boolean {
  return Object.prototype.hasOwnProperty.call(CURRENCY_MINOR_DIGITS, code);
}

export function minorDigitsFor(currencyCode: string): number {
  const digits = CURRENCY_MINOR_DIGITS[currencyCode];
  if (digits === undefined) {
    throw new Error(`minorDigitsFor called with unsupported currency "${currencyCode}"`);
  }
  return digits;
}

/**
 * Accepts exactly one shape: an optional sign (leading '-' XOR wrapping
 * parentheses, never both), digits, and — for currencies with minor units —
 * an optional single '.' followed by 1..N fractional digits where N is the
 * currency's minor-unit digit count. No thousands separators, no currency
 * symbols, no whitespace inside the number. Real machine-generated exports
 * (Stripe's CSV reports included) use plain decimals with no such
 * decoration, so this is not a usability regression — it's closing off the
 * exact ambiguity ("was that a thousands comma or a decimal comma?") that
 * caused silent misparses before.
 */
export function parseStrictMoney(raw: string | undefined | null, currencyCode: string, field: string): MoneyResult {
  if (!isSupportedCurrency(currencyCode)) {
    return err("unsupported_currency", field, `Unsupported currency "${currencyCode}" for field ${field}`);
  }
  const minorDigits = CURRENCY_MINOR_DIGITS[currencyCode]!;

  if (raw === undefined || raw === null) {
    return err("missing_amount", field, `${field} is required`);
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    return err("blank_amount", field, `${field} must not be blank`);
  }
  if (/\s/.test(trimmed)) {
    return err("malformed_amount", field, `${field} value "${raw}" contains embedded whitespace`);
  }

  const decimalCount = (trimmed.match(/\./g) ?? []).length;
  if (decimalCount > 1) {
    return err("multiple_decimal_points", field, `${field} value "${raw}" has more than one decimal point`);
  }

  const parenNegative = /^\(.*\)$/.test(trimmed);
  const body = parenNegative ? trimmed.slice(1, -1) : trimmed;
  if (parenNegative && body.includes("-")) {
    return err("malformed_amount", field, `${field} value "${raw}" mixes parentheses and a minus sign`);
  }

  const pattern = minorDigits > 0 ? new RegExp(`^-?\\d+(\\.\\d{1,${minorDigits}})?$`) : /^-?\d+$/;

  if (!pattern.test(body)) {
    if (/[^0-9.\-]/.test(body)) {
      return err(
        "invalid_characters",
        field,
        `${field} value "${raw}" contains characters that are not part of a plain number`
      );
    }
    const fracMatch = body.match(/\.(\d+)$/);
    if (fracMatch && fracMatch[1]!.length > minorDigits) {
      return err(
        "excess_precision",
        field,
        `${field} value "${raw}" has more decimal precision than ${currencyCode} supports (${minorDigits} digit(s))`
      );
    }
    return err("malformed_amount", field, `${field} value "${raw}" is not a valid plain ${currencyCode} amount`);
  }

  const negative = parenNegative || body.startsWith("-");
  const unsigned = body.replace(/^-/, "");
  const [wholeRaw, fracRaw = ""] = unsigned.split(".");
  const whole = wholeRaw === "" ? "0" : wholeRaw;
  const frac = frac_pad(fracRaw, minorDigits);

  const scale = 10 ** minorDigits;
  const wholeNum = Number(whole);
  const fracNum = minorDigits > 0 ? Number(frac) : 0;

  if (!Number.isFinite(wholeNum) || !Number.isFinite(fracNum)) {
    return err("malformed_amount", field, `${field} value "${raw}" could not be parsed as a number`);
  }

  const cents = wholeNum * scale + fracNum;
  if (!Number.isSafeInteger(cents)) {
    return err("unsafe_integer", field, `${field} value "${raw}" is outside the safe integer range`);
  }

  return { ok: true, cents: negative ? -cents : cents };
}

function frac_pad(fracRaw: string, minorDigits: number): string {
  if (minorDigits === 0) return "";
  return fracRaw.padEnd(minorDigits, "0");
}

export function centsToDecimalString(cents: number, currencyCode: string): string {
  const minorDigits = isSupportedCurrency(currencyCode) ? CURRENCY_MINOR_DIGITS[currencyCode]! : 2;
  const negative = cents < 0;
  const abs = Math.abs(cents);
  const scale = 10 ** minorDigits;
  const whole = Math.floor(abs / scale);
  const frac = abs % scale;
  const fracStr = minorDigits > 0 ? "." + frac.toString().padStart(minorDigits, "0") : "";
  return `${negative ? "-" : ""}${whole}${fracStr}`;
}
