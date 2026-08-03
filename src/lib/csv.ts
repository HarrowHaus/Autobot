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
