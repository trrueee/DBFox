export async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    return false;
  }
}

const DANGEROUS_CSV_PREFIXES = new Set(["=", "+", "-", "@"]);

// Keep this list aligned with engine/sql/execution/csv_export.py.  Spreadsheet
// programs can ignore these leading characters before evaluating a formula.
const CSV_UNICODE_WHITESPACE_CODE_POINTS = new Set([
  0x0020,
  0x00a0,
  0x1680,
  0x2000,
  0x2001,
  0x2002,
  0x2003,
  0x2004,
  0x2005,
  0x2006,
  0x2007,
  0x2008,
  0x2009,
  0x200a,
  0x2028,
  0x2029,
  0x202f,
  0x205f,
  0x3000,
]);
const NEGATIVE_DECIMAL_LITERAL = /^-(?:(?:[0-9]+(?:\.[0-9]*)?)|(?:\.[0-9]+))(?:[eE][+-]?[0-9]+)?$/;

function isCsvLeadingIgnorable(codePoint: number) {
  return (
    codePoint === 0xfeff ||
    (codePoint >= 0x0000 && codePoint <= 0x001f) ||
    (codePoint >= 0x007f && codePoint <= 0x009f) ||
    CSV_UNICODE_WHITESPACE_CODE_POINTS.has(codePoint)
  );
}

function csvFormulaCandidate(text: string) {
  let index = 0;
  while (index < text.length) {
    const codePoint = text.codePointAt(index);
    if (codePoint === undefined || !isCsvLeadingIgnorable(codePoint)) break;
    index += codePoint > 0xffff ? 2 : 1;
  }
  return text.slice(index);
}

/**
 * Render a CSV cell as text when a spreadsheet could otherwise evaluate it.
 *
 * The leading BOM, Unicode/ASCII whitespace, and control characters are only
 * ignored for detection; the original value is retained after the apostrophe.
 * Canonical negative decimal/exponent literals remain numeric data.
 */
export function escapeCsvCell(value: unknown) {
  const text = value === null || value === undefined ? "" : String(value);
  const candidate = csvFormulaCandidate(text);
  if (!candidate || !DANGEROUS_CSV_PREFIXES.has(candidate[0])) return text;
  if (candidate[0] === "-" && NEGATIVE_DECIMAL_LITERAL.test(candidate)) return text;
  return `'${text}`;
}

export function downloadTextFile(filename: string, content: string, mimeType = "text/plain;charset=utf-8") {
  try {
    const blob = new Blob([content], { type: mimeType });
    return downloadBlobFile(filename, blob);
  } catch {
    return false;
  }
}

export function downloadBlobFile(filename: string, blob: Blob) {
  try {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
    return true;
  } catch {
    return false;
  }
}

export function toCsv(columns: string[], rows: string[][]) {
  const quote = (value: unknown) => `"${escapeCsvCell(value).replaceAll('"', '""')}"`;
  return [columns.map(quote).join(","), ...rows.map((row) => row.map(quote).join(","))].join("\n");
}
