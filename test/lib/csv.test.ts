import { describe, expect, it } from "vitest";
import { parseCsv, parseCsvRecords, sanitizeCsvCell, toCsv } from "../../src/lib/csv.js";

describe("parseCsv", () => {
  it("parses simple rows", () => {
    expect(parseCsv("a,b,c\n1,2,3\n")).toEqual([
      ["a", "b", "c"],
      ["1", "2", "3"],
    ]);
  });

  it("handles quoted fields with embedded commas and quotes", () => {
    const rows = parseCsv('a,b\n"hello, world","she said ""hi"""\n');
    expect(rows).toEqual([
      ["a", "b"],
      ["hello, world", 'she said "hi"'],
    ]);
  });

  it("handles files without a trailing newline", () => {
    expect(parseCsv("a,b\n1,2")).toEqual([
      ["a", "b"],
      ["1", "2"],
    ]);
  });
});

describe("parseCsvRecords", () => {
  it("maps rows to header-keyed records", () => {
    const records = parseCsvRecords("Name,Amount\nAlice,10.00\nBob,20.00\n");
    expect(records).toEqual([
      { Name: "Alice", Amount: "10.00" },
      { Name: "Bob", Amount: "20.00" },
    ]);
  });
});

describe("toCsv", () => {
  it("quotes fields containing commas", () => {
    const csv = toCsv(["a", "b"], [["x,y", "z"]]);
    expect(csv).toBe('a,b\r\n"x,y",z\r\n');
  });
});

// Regression coverage for OWASP CSV/formula injection: a cell that starts
// with a formula-trigger character must never reach an output file
// unescaped, since Excel/Sheets/Numbers will execute it on open (e.g.
// =cmd|'/C calc'!A0 in old Excel, or a DDE/webhook exfil formula).
describe("sanitizeCsvCell — formula injection", () => {
  it.each([
    ["=cmd|'/C calc'!A0", "'=cmd|'/C calc'!A0"],
    ["+1+1", "'+1+1"],
    ["-2+3+cmd|' /C calc'!A1", "'-2+3+cmd|' /C calc'!A1"],
    ["@SUM(1+1)", "'@SUM(1+1)"],
    ["\tmalicious", "'\tmalicious"],
    ["\rmalicious", "'\rmalicious"],
  ])("prefixes %s with an apostrophe to force plain text", (input, expected) => {
    expect(sanitizeCsvCell(input)).toBe(expected);
  });

  it("leaves plain numbers untouched, including negative amounts", () => {
    expect(sanitizeCsvCell("100.00")).toBe("100.00");
    expect(sanitizeCsvCell("-43.70")).toBe("-43.70");
    expect(sanitizeCsvCell("0")).toBe("0");
  });

  it("leaves ISO dates untouched", () => {
    expect(sanitizeCsvCell("2026-01-15")).toBe("2026-01-15");
  });

  it("leaves ordinary text untouched", () => {
    expect(sanitizeCsvCell("Stripe payout po_123")).toBe("Stripe payout po_123");
  });

  it("propagates through toCsv so a malicious cell never reaches the file unescaped", () => {
    const csv = toCsv(["Description"], [["=HYPERLINK(\"http://evil.example\",\"click\")"]]);
    expect(csv).toBe('Description\r\n"\'=HYPERLINK(""http://evil.example"",""click"")"\r\n');
    expect(csv.split("\n")[1]!.startsWith('"\'')).toBe(true);
  });
});
