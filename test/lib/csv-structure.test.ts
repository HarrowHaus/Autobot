import { describe, expect, it } from "vitest";
import { MAX_COLUMNS, MAX_FIELD_CHARS, parseCsvStructured } from "../../src/lib/csv.js";

describe("parseCsvStructured — accepts well-formed input", () => {
  it("returns header and records for a clean file", () => {
    const result = parseCsvStructured("a,b\n1,2\n3,4\n");
    expect(result.ok).toBe(true);
    expect(result.header).toEqual(["a", "b"]);
    expect(result.records).toEqual([
      { a: "1", b: "2" },
      { a: "3", b: "4" },
    ]);
  });

  it("accepts properly escaped quotes inside quoted fields", () => {
    const result = parseCsvStructured('a,b\n"he said ""hi""","x,y"\n');
    expect(result.ok).toBe(true);
    expect(result.records[0]).toEqual({ a: 'he said "hi"', b: "x,y" });
  });

  it("accepts a header-only file with no data rows", () => {
    const result = parseCsvStructured("a,b\n");
    expect(result.ok).toBe(true);
    expect(result.records).toEqual([]);
  });
});

describe("parseCsvStructured — rejects malformed quote structure", () => {
  it("rejects an unterminated quoted field rather than swallowing later rows", () => {
    // Without this check the stray quote merges rows 1 and 2 into one cell,
    // silently changing every total computed downstream.
    const result = parseCsvStructured('a,b\n"oops,2\n3,4\n');
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("malformed_quotes");
  });

  it("does not false-positive on a fully escaped quote run", () => {
    expect(parseCsvStructured('a\n""""\n').ok).toBe(true);
  });
});

describe("parseCsvStructured — rejects ambiguous headers", () => {
  it("rejects duplicate column names", () => {
    const result = parseCsvStructured("gross,fee,gross\n1,2,3\n");
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("duplicate_column");
  });

  it("treats duplicate column names case-insensitively", () => {
    const result = parseCsvStructured("Gross,fee,GROSS\n1,2,3\n");
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("duplicate_column");
  });

  it("rejects a blank column name", () => {
    const result = parseCsvStructured("a,,c\n1,2,3\n");
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("blank_column_name");
  });

  it("rejects a file with more than MAX_COLUMNS columns", () => {
    const header = Array.from({ length: MAX_COLUMNS + 1 }, (_, i) => `c${i}`).join(",");
    const result = parseCsvStructured(`${header}\n`);
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("too_many_columns");
  });
});

describe("parseCsvStructured — rejects malformed rows", () => {
  it("rejects a row with fewer fields than the header", () => {
    const result = parseCsvStructured("a,b,c\n1,2\n");
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("inconsistent_row_width");
    expect(result.errors[0]!.message).toContain("Row 1");
  });

  it("rejects a row with more fields than the header", () => {
    const result = parseCsvStructured("a,b\n1,2,3\n");
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("inconsistent_row_width");
  });

  it("reports every malformed row, not just the first", () => {
    const result = parseCsvStructured("a,b\n1\n2\n3,4\n5\n");
    expect(result.ok).toBe(false);
    expect(result.errors.filter((e) => e.code === "inconsistent_row_width")).toHaveLength(3);
  });

  it("rejects an excessively long field", () => {
    const result = parseCsvStructured(`a,b\n1,${"x".repeat(MAX_FIELD_CHARS + 1)}\n`);
    expect(result.ok).toBe(false);
    expect(result.errors[0]!.code).toBe("field_too_long");
  });

  it("accepts a field exactly at the length limit", () => {
    const result = parseCsvStructured(`a,b\n1,${"x".repeat(MAX_FIELD_CHARS)}\n`);
    expect(result.ok).toBe(true);
  });
});
