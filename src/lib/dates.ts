/**
 * Calendar-accurate date validation.
 *
 * A regex like /^\d{4}-\d{2}-\d{2}/ happily accepts 2026-02-30, 2026-13-01,
 * and 2025-02-29 — none of which are real days. For a reconciliation report
 * whose whole purpose is telling someone which day money moved, silently
 * accepting an impossible date is worse than rejecting the file.
 */

export interface ParsedDate {
  ok: boolean;
  /** Normalized YYYY-MM-DD, present only when ok. */
  date?: string;
  reason?: string;
}

const ISO_DATE_PREFIX = /^(\d{4})-(\d{2})-(\d{2})(?:[T ]|$)/;

function isLeapYear(year: number): boolean {
  return (year % 4 === 0 && year % 100 !== 0) || year % 400 === 0;
}

function daysInMonth(year: number, month: number): number {
  const lengths = [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  return lengths[month - 1]!;
}

/**
 * Extracts and validates the calendar date at the start of a timestamp
 * string. Accepts "2026-01-15", "2026-01-15 00:00:00", and
 * "2026-01-15T00:00:00Z"; rejects anything whose date component is not a
 * real day.
 */
export function parseCalendarDate(raw: string | undefined | null): ParsedDate {
  if (raw === undefined || raw === null) {
    return { ok: false, reason: "missing" };
  }
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: false, reason: "blank" };
  }

  const match = ISO_DATE_PREFIX.exec(trimmed);
  if (!match) {
    return { ok: false, reason: `"${trimmed}" is not an ISO-8601 (YYYY-MM-DD) date` };
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);

  if (month < 1 || month > 12) {
    return { ok: false, reason: `month ${match[2]} in "${trimmed}" is not a real month` };
  }
  const maxDay = daysInMonth(year, month);
  if (day < 1 || day > maxDay) {
    return {
      ok: false,
      reason: `day ${match[3]} in "${trimmed}" is not a real day (${match[1]}-${match[2]} has ${maxDay} days)`,
    };
  }

  return { ok: true, date: `${match[1]}-${match[2]}-${match[3]}` };
}
