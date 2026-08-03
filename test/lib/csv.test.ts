import { describe, expect, it } from "vitest";
import { parseCsv, parseCsvRecords, toCsv } from "../../src/lib/csv.js";

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
