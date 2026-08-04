import { describe, expect, it } from "vitest";
import { parseCalendarDate } from "../../src/lib/dates.js";

describe("parseCalendarDate — accepts real dates", () => {
  it.each([
    ["2026-01-15", "2026-01-15"],
    ["2026-01-15 00:00:00", "2026-01-15"],
    ["2026-01-15T09:30:00Z", "2026-01-15"],
    ["2024-02-29", "2024-02-29"], // leap year
    ["2000-02-29", "2000-02-29"], // divisible by 400
    ["2026-12-31", "2026-12-31"],
  ])("accepts %s", (input, expected) => {
    expect(parseCalendarDate(input)).toEqual({ ok: true, date: expected });
  });
});

describe("parseCalendarDate — rejects impossible dates a regex would accept", () => {
  it.each([
    ["2026-02-30", "day"],
    ["2026-13-01", "month"],
    ["2026-00-10", "month"],
    ["2026-01-00", "day"],
    ["2026-01-32", "day"],
    ["2025-02-29", "day"], // not a leap year
    ["1900-02-29", "day"], // divisible by 100 but not 400
    ["2026-04-31", "day"], // April has 30
  ])("rejects %s", (input, expectedReasonFragment) => {
    const result = parseCalendarDate(input);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain(expectedReasonFragment);
  });
});

describe("parseCalendarDate — rejects non-dates", () => {
  it.each([
    [undefined, "missing"],
    [null, "missing"],
    ["", "blank"],
    ["   ", "blank"],
    ["not a date", "ISO-8601"],
    ["15/01/2026", "ISO-8601"],
    ["2026-1-5", "ISO-8601"],
    ["20260115", "ISO-8601"],
  ])("rejects %s", (input, expectedReasonFragment) => {
    const result = parseCalendarDate(input as string | undefined | null);
    expect(result.ok).toBe(false);
    expect(result.reason).toContain(expectedReasonFragment);
  });

  it("rejects a date glued to trailing characters without a separator", () => {
    expect(parseCalendarDate("2026-01-15abc").ok).toBe(false);
  });
});
