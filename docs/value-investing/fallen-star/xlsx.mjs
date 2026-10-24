// Small, dependency-free XLSX writer for the shared Fallen Star tables.
const encoder = new TextEncoder();

function xml(value) {
  return String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&apos;");
}

function columnName(index) {
  let result = "";
  for (let n = index + 1; n > 0; n = Math.floor((n - 1) / 26)) {
    result = String.fromCharCode(65 + ((n - 1) % 26)) + result;
  }
  return result;
}

function cell(ref, value, type = "text") {
  if (value === null || value === undefined || value === "") return "";
  if (type === "date" || type === "month") {
    const iso = type === "month" ? `${value}-01` : String(value);
    const timestamp = Date.parse(`${iso}T00:00:00Z`);
    if (Number.isFinite(timestamp)) {
      const serial = timestamp / 86400000 + 25569;
      return `<c r="${ref}" s="${type === "date" ? 1 : 2}"><v>${serial}</v></c>`;
    }
  }
  if (["percent", "decimal", "integer"].includes(type) && Number.isFinite(Number(value))) {
    const style = { percent: 3, decimal: 4, integer: 5 }[type];
    return `<c r="${ref}" s="${style}"><v>${Number(value)}</v></c>`;
  }
  return `<c r="${ref}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
}

function worksheet(columns, rows, filter = true) {
  const width = Math.max(1, columns.length);
  const last = `${columnName(width - 1)}${rows.length + 1}`;
  const parts = [
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
    `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:${last}"/>`,
    '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>',
    '<sheetFormatPr defaultRowHeight="15"/><cols>',
  ];
  columns.forEach((col, i) => parts.push(`<col min="${i + 1}" max="${i + 1}" width="${Math.max(14, Math.min(42, col.width || col.label.length + 5))}" customWidth="1"/>`));
  parts.push('</cols><sheetData><row r="1">');
  columns.forEach((col, i) => parts.push(cell(`${columnName(i)}1`, col.label)));
  parts.push('</row>');
  rows.forEach((row, rowIndex) => {
    const number = rowIndex + 2;
    parts.push(`<row r="${number}">`);
    columns.forEach((col, i) => parts.push(cell(`${columnName(i)}${number}`, col.value(row), col.type)));
    parts.push('</row>');
  });
  parts.push('</sheetData>');
  if (filter) parts.push(`<autoFilter ref="A1:${last}"/>`);
  parts.push('</worksheet>');
  return parts.join("");
}

const styles = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="4"><numFmt numFmtId="164" formatCode="yyyy-mm-dd"/><numFmt numFmtId="165" formatCode="mmm yyyy"/><numFmt numFmtId="166" formatCode="0.0%"/><numFmt numFmtId="167" formatCode="0.00"/></numFmts>
<fonts count="1"><font><sz val="11"/><name val="Aptos"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border/></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="6"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="167" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/><xf numFmtId="1" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>`;

function crc32(bytes) {
  let crc = 0xffffffff;
  for (const byte of bytes) {
    crc ^= byte;
    for (let bit = 0; bit < 8; bit++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
  }
  return (crc ^ 0xffffffff) >>> 0;
}

function zip(files) {
  const local = [];
  const central = [];
  let offset = 0;
  for (const [name, content] of files) {
    const nameBytes = encoder.encode(name);
    const bytes = encoder.encode(content);
    const checksum = crc32(bytes);
    const header = new Uint8Array(30 + nameBytes.length);
    const view = new DataView(header.buffer);
    view.setUint32(0, 0x04034b50, true);
    view.setUint16(4, 20, true);
    view.setUint16(6, 0x0800, true);
    view.setUint32(14, checksum, true);
    view.setUint32(18, bytes.length, true);
    view.setUint32(22, bytes.length, true);
    view.setUint16(26, nameBytes.length, true);
    header.set(nameBytes, 30);
    local.push(header, bytes);

    const directory = new Uint8Array(46 + nameBytes.length);
    const directoryView = new DataView(directory.buffer);
    directoryView.setUint32(0, 0x02014b50, true);
    directoryView.setUint16(4, 20, true);
    directoryView.setUint16(6, 20, true);
    directoryView.setUint16(8, 0x0800, true);
    directoryView.setUint32(16, checksum, true);
    directoryView.setUint32(20, bytes.length, true);
    directoryView.setUint32(24, bytes.length, true);
    directoryView.setUint16(28, nameBytes.length, true);
    directoryView.setUint32(42, offset, true);
    directory.set(nameBytes, 46);
    central.push(directory);
    offset += header.length + bytes.length;
  }
  const centralLength = central.reduce((sum, part) => sum + part.length, 0);
  const end = new Uint8Array(22);
  const endView = new DataView(end.buffer);
  endView.setUint32(0, 0x06054b50, true);
  endView.setUint16(8, files.length, true);
  endView.setUint16(10, files.length, true);
  endView.setUint32(12, centralLength, true);
  endView.setUint32(16, offset, true);
  const output = new Uint8Array(offset + centralLength + end.length);
  let position = 0;
  for (const part of [...local, ...central, end]) {
    output.set(part, position);
    position += part.length;
  }
  return output;
}

export function buildXlsx(columns, rows, metadata = {}) {
  const exportColumns = columns.filter(col => col.exportable !== false).map(col => ({
    label: col.label, type: col.type || "text", width: col.width,
    value: row => col.exportValue ? col.exportValue(row) : row[col.key],
  }));
  const metadataRows = Object.entries(metadata).map(([key, value]) => ({ key, value: value ?? "" }));
  const metaColumns = [
    { label: "Field", value: row => row.key, width: 25 },
    { label: "Value", value: row => row.value, width: 38 },
  ];
  const files = [
    ["[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'],
    ["_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'],
    ["xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Results" sheetId="1" r:id="rId1"/><sheet name="Metadata" sheetId="2" r:id="rId2"/></sheets></workbook>'],
    ["xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/><Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'],
    ["xl/styles.xml", styles],
    ["xl/worksheets/sheet1.xml", worksheet(exportColumns, rows)],
    ["xl/worksheets/sheet2.xml", worksheet(metaColumns, metadataRows, false)],
  ];
  return zip(files);
}

export function downloadXlsx(columns, rows, metadata, filename) {
  const blob = new Blob([buildXlsx(columns, rows, metadata)], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename.replace(/[^a-z0-9._-]/gi, "_");
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}
