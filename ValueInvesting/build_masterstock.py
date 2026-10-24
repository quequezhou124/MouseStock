"""Build the ValueInvesting names-only union of U.S. and Canadian listed stocks.

Inputs are snapshots of Nasdaq Trader's nasdaqlisted/otherlisted directories and
a TMX-derived TSX/TSXV issuer CSV (see source URLs below). The workbook stays in
ValueInvesting and the matching website data is written to docs/value-investing.
This script uses only the Python standard library, including the minimal XLSX writer.
"""

import csv
import json
import re
import urllib.request
import xml.sax.saxutils as xml
import zipfile
from pathlib import Path


ROOT = Path(__file__).parent
SOURCES = {
    "nasdaq": "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt",
    "other_us": "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt",
    "canada": "https://raw.githubusercontent.com/benjaminpo/finance-dataset/main/config/listings/tsx-listed-symbols.csv",
    "cse": "https://website-data-api-v2.thecse.com/api/companies/all",
}


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(request, timeout=30).read().decode("utf-8-sig")


def clean_name(name):
    name = re.sub(r"\s+", " ", name).strip(" ,-.")
    # U.S. directories append issue descriptions; keep the issuer name.
    name = re.sub(r"\s+-\s+(?:Class [A-Z0-9]+ )?(?:Common Stock|Ordinary Shares?|Common Shares?|American Depositary Shares?|ADS|Subordinate Voting Shares?|Voting Shares?).*$", "", name, flags=re.I)
    name = re.sub(r"\s+(?:Class [A-Z0-9]+ )?(?:Common Stock|Ordinary Shares?|Common Shares?|American Depositary Shares?|Subordinate Voting Shares?|Voting Shares?)(?: of Beneficial Interest)?\s*$", "", name, flags=re.I)
    name = re.sub(r"\s+-\s+Class [A-Z0-9]+ Shares?$", "", name, flags=re.I)
    return name.strip(" ,-.")


def us_stock(row):
    if row.get("Test Issue") != "N" or row.get("ETF") != "N":
        return False
    # Nasdaq Trader's directories also carry an exchange/category identifier.
    # Accept only Nasdaq tiers or the named U.S. national listing exchanges;
    # any OTC or unrecognized market is excluded even if present in a feed.
    if "Market Category" in row and row["Market Category"] not in {"Q", "G", "S"}:
        return False
    if "Exchange" in row and row["Exchange"] not in {"A", "N", "P", "Z", "V", "F"}:
        return False
    name = row["Security Name"]
    symbol = row.get("Symbol") or row.get("ACT Symbol", "")
    if re.search(r"(?:\^|\.)(?:W|WS|R|U|P)(?:$|\d)", symbol, re.I):
        return False
    if re.search(r"\b(?:warrants?|rights?|preferred|preference|debentures?|notes?|bonds?|ETFs?|ETNs?|units?)\b", name, re.I):
        return False
    if re.search(r"\b(?:fund|portfolio)\b", name, re.I):
        return False
    if re.search(r"\b(?:due 20\d\d|fixed.rate|floating.rate|senior debt|subordinated debt)\b", name, re.I):
        return False
    return True


def canada_stock(row):
    name = row["Name"]
    symbol = row["Symbol"]
    if row["Market"] not in {"TSX", "TSXV"}:
        return False
    if re.search(r"\b(?:ETF|ETFTM|ETN|ETP|CDR|Fund|Portfolio|Warrant|Preferred|Debenture|Bond|Note)\b", name, re.I):
        return False
    if re.search(r"(?:-P\.|-PR\.|-WT\.|-W\.|-U\.|-J\.|-L\.)", symbol, re.I):
        # -P.V denotes TSXV capital pool companies' common shares; keep those.
        if not symbol.endswith("-P.V"):
            return False
    return True


def xlsx(names, path):
    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:A%d"/><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols><col min="1" max="1" width="52" customWidth="1"/></cols><sheetData>' % (len(names)+1)]
    for i, name in enumerate(["Company Name", *names], 1):
        sheet.append('<row r="%d"><c r="A%d" t="inlineStr"><is><t>%s</t></is></c></row>' % (i, i, xml.escape(name)))
    sheet.append('</sheetData><autoFilter ref="A1:A%d"/></worksheet>' % (len(names)+1))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        z.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Master Stock List" sheetId="1" r:id="rId1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", "".join(sheet))


def main():
    names = {}
    counts = {}
    for key in ("nasdaq", "other_us"):
        rows = csv.DictReader(fetch(SOURCES[key]).splitlines(), delimiter="|")
        picked = [clean_name(r["Security Name"]) for r in rows if us_stock(r)]
        counts[key] = len(picked)
        for name in picked:
            if name:
                names.setdefault(name.casefold(), name)
    rows = csv.DictReader(fetch(SOURCES["canada"]).splitlines())
    picked = [clean_name(r["Name"]) for r in rows if canada_stock(r)]
    counts["canada"] = len(picked)
    for name in picked:
        if name:
            names.setdefault(name.casefold(), name)
    cse_rows = json.loads(fetch(SOURCES["cse"]))
    picked = [clean_name(r["securityName"]) for r in cse_rows
              if r["status"] == "Active"
              and not re.search(r"\b(?:ETF|ETFTM|ETN|ETP|CDR|Fund|Portfolio|Warrant|Preferred|Debenture|Bond|Note)\b", r["securityName"], re.I)]
    counts["cse"] = len(picked)
    for name in picked:
        if name:
            names.setdefault(name.casefold(), name)
    result = sorted(names.values(), key=str.casefold)
    path = ROOT / "masterstockexcel.xlsx"
    xlsx(result, path)
    site_data = ROOT.parent / "docs" / "value-investing" / "masterlist" / "stocks.json"
    site_data.parent.mkdir(parents=True, exist_ok=True)
    site_data.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(path)
    print("source rows", counts)
    print("unique names", len(result))


if __name__ == "__main__":
    main()
