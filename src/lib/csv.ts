/**
 * Minimal RFC-4180-ish CSV parse/stringify. No external dependency:
 * processor exports use a well-known, controlled set of columns, and
 * hand-rolled parsing keeps the bundle tiny and behavior fully auditable.
 */

export function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;
  // Normalize line endings up front so \r\n and \r don't leak into fields.
  const src = text.replace(/\r\n/g, "\n").replace(/\r/g, "\n");

  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (inQuotes) {
      if (ch === '"') {
        if (src[i + 1] === '"') {
          field += '"';
          i++;
        } else {
          inQuotes = false;
        }
      } else {
        field += ch;
      }
      continue;
    }

    if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      row.push(field);
      field = "";
    } else if (ch === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += ch;
    }
  }
  // Flush trailing field/row (files may or may not end with a newline).
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((r) => !(r.length === 1 && r[0] === ""));
}

export function parseCsvRecords(text: string): Record<string, string>[] {
  const rows = parseCsv(text);
  if (rows.length === 0) return [];
  const header = rows[0]!.map((h) => h.trim());
  return rows.slice(1).map((r) => {
    const rec: Record<string, string> = {};
    header.forEach((h, i) => {
      rec[h] = (r[i] ?? "").trim();
    });
    return rec;
  });
}

/**
 * Structural limits. These are not accounting rules — they exist so that a
 * malformed or hostile file is rejected with a clear message before any
 * money logic runs on it, rather than being silently reshaped into
 * something parseable-but-wrong.
 */
export const MAX_COLUMNS = 250;
export const MAX_FIELD_CHARS = 10_000;

export interface CsvStructureError {
  code: string;
  field: string;
  message: string;
}

export interface CsvStructureResult {
  ok: boolean;
  header: string[];
  records: Record<string, string>[];
  errors: CsvStructureError[];
}

/**
 * Parses a CSV and enforces structural integrity BEFORE any field is
 * interpreted. The plain parseCsv() above is forgiving by design (it will
 * happily absorb an unterminated quote or a short row); for financial input
 * that forgiveness is a hazard, because a single stray quote can silently
 * merge two rows into one and change totals without producing any visible
 * error. This function refuses instead.
 */
export function parseCsvStructured(text: string): CsvStructureResult {
  const empty = { header: [] as string[], records: [] as Record<string, string>[] };
  const fail = (code: string, field: string, message: string): CsvStructureResult => ({
    ok: false,
    ...empty,
    errors: [{ code, field, message }],
  });

  // An odd number of unescaped quotes means a field was never closed, which
  // would otherwise swallow every subsequent row into one giant cell.
  if (hasUnterminatedQuote(text)) {
    return fail(
      "malformed_quotes",
      "file",
      "The file has an unterminated quoted field. A stray double-quote can silently merge rows together, so the file is rejected rather than parsed."
    );
  }

  const rows = parseCsv(text);
  if (rows.length === 0) {
    return fail("empty_file", "file", "The uploaded file has no rows.");
  }

  const rawHeader = rows[0]!.map((h) => h.trim());

  if (rawHeader.length > MAX_COLUMNS) {
    return fail(
      "too_many_columns",
      "header",
      `The file has ${rawHeader.length} columns, which exceeds the ${MAX_COLUMNS}-column limit.`
    );
  }

  const blankHeaderIndex = rawHeader.findIndex((h) => h === "");
  if (blankHeaderIndex !== -1) {
    return fail(
      "blank_column_name",
      "header",
      `Column ${blankHeaderIndex + 1} has no name. Every column must be named so its values can be attributed unambiguously.`
    );
  }

  // Duplicate headers are fatal: record-building is last-write-wins, so a
  // repeated column name would silently discard one of the two columns.
  const seen = new Map<string, number>();
  for (const [i, name] of rawHeader.entries()) {
    const key = name.toLowerCase();
    const previous = seen.get(key);
    if (previous !== undefined) {
      return fail(
        "duplicate_column",
        "header",
        `Column "${name}" appears more than once (positions ${previous + 1} and ${i + 1}). Duplicate column names make row values ambiguous.`
      );
    }
    seen.set(key, i);
  }

  const errors: CsvStructureError[] = [];
  const dataRows = rows.slice(1);

  for (const [i, row] of dataRows.entries()) {
    const rowNumber = i + 1;
    if (row.length !== rawHeader.length) {
      errors.push({
        code: "inconsistent_row_width",
        field: "file",
        message: `Row ${rowNumber} has ${row.length} field(s) but the header declares ${rawHeader.length}.`,
      });
      continue;
    }
    const longFieldIndex = row.findIndex((f) => f.length > MAX_FIELD_CHARS);
    if (longFieldIndex !== -1) {
      errors.push({
        code: "field_too_long",
        field: rawHeader[longFieldIndex] ?? String(longFieldIndex),
        message: `Row ${rowNumber}, column "${rawHeader[longFieldIndex]}" exceeds the ${MAX_FIELD_CHARS}-character limit.`,
      });
    }
  }

  if (errors.length > 0) {
    return { ok: false, ...empty, errors };
  }

  const records = dataRows.map((r) => {
    const rec: Record<string, string> = {};
    rawHeader.forEach((h, i) => {
      rec[h] = (r[i] ?? "").trim();
    });
    return rec;
  });

  return { ok: true, header: rawHeader, records, errors: [] };
}

function hasUnterminatedQuote(text: string): boolean {
  let inQuotes = false;
  for (let i = 0; i < text.length; i++) {
    if (text[i] !== '"') continue;
    if (inQuotes && text[i + 1] === '"') {
      i++; // escaped quote inside a quoted field
      continue;
    }
    inQuotes = !inQuotes;
  }
  return inQuotes;
}

// A cell that is a plain number or an ISO date is never a formula, however
// it starts — this lets legitimate negative amounts like "-43.70" through
// untouched while still catching the actual injection vector: attacker-
// controlled text (descriptions, IDs) that happens to start with a
// spreadsheet-formula trigger character.
const PURE_NUMBER_OR_DATE = /^-?\d+(\.\d+)?$|^\d{4}-\d{2}-\d{2}$/;
// OWASP CSV-injection trigger characters: = + @ and the raw tab/CR bytes,
// which some spreadsheet implementations also treat as formula starts.
const RISKY_LEADING_CHAR = /^[=+@\t\r]/;

/**
 * Neutralizes CSV formula injection in a single cell. Text starting with a
 * formula-trigger character is prefixed with a leading apostrophe, which
 * every major spreadsheet application treats as "force this cell to plain
 * text" rather than evaluating it. Pure numbers/dates (including negative
 * amounts) are left untouched since they are never formulas and quoting
 * them would corrupt legitimate accounting data on import.
 */
export function sanitizeCsvCell(value: string): string {
  if (PURE_NUMBER_OR_DATE.test(value)) return value;
  if (RISKY_LEADING_CHAR.test(value)) return `'${value}`;
  // A bare leading '-' followed by anything that isn't purely more digits
  // is also a documented injection vector (e.g. "-2+3+cmd|...!A1") — the
  // PURE_NUMBER_OR_DATE check above only exempts genuine plain numbers, so
  // anything else starting with '-' reaches here and gets neutralized too.
  if (value.startsWith("-")) return `'${value}`;
  return value;
}

function csvEscape(value: string | number): string {
  const s = sanitizeCsvCell(String(value));
  if (s.includes(",") || s.includes('"') || s.includes("\n")) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCsv(header: string[], rows: (string | number)[][]): string {
  const lines = [header.map((h) => csvEscape(h)).join(",")];
  for (const row of rows) {
    lines.push(row.map(csvEscape).join(","));
  }
  return lines.join("\r\n") + "\r\n";
}
