import { downloadXlsx } from "./xlsx.mjs";

function compare(a, b, type) {
  if (["percent", "decimal", "integer"].includes(type)) return Number(a) - Number(b);
  return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: "base" });
}

export class DataTable {
  constructor(host, { title, columns, filename, initialSort = null, emptyMessage = "No rows match these filters." }) {
    this.host = host;
    this.columns = columns;
    this.filename = filename;
    this.emptyMessage = emptyMessage;
    this.sort = initialSort;
    this.rows = [];
    this.metadata = {};

    this.root = document.createElement("section");
    this.root.className = "data-table";
    const toolbar = document.createElement("div");
    toolbar.className = "data-table-toolbar";
    const heading = document.createElement("div");
    heading.className = "data-table-title";
    const name = document.createElement("h3");
    name.textContent = title;
    this.count = document.createElement("span");
    heading.append(name, this.count);
    this.download = document.createElement("button");
    this.download.type = "button";
    this.download.className = "download-excel";
    this.download.textContent = "Download Excel";
    this.download.addEventListener("click", () => {
      const metadata = { ...this.metadata, "Row count": this.rows.length };
      if (this.sort) metadata["Sort order"] = `${this.columnLabel(this.sort.key)} (${this.sort.direction})`;
      downloadXlsx(this.columns, this.sortedRows(), metadata, this.filename(this.metadata));
    });
    toolbar.append(heading, this.download);
    this.scroll = document.createElement("div");
    this.scroll.className = "data-table-scroll";
    this.scroll.tabIndex = 0;
    this.scroll.setAttribute("role", "region");
    this.scroll.setAttribute("aria-label", `${title} table, scroll for more rows or columns`);
    this.table = document.createElement("table");
    this.table.className = "fallen-data-table";
    this.table.createTHead();
    this.body = this.table.createTBody();
    this.scroll.append(this.table);
    this.root.append(toolbar, this.scroll);
    this.host.replaceChildren(this.root);
    this.renderHead();
    this.renderRows();
  }

  columnLabel(key) {
    return this.columns.find(col => col.key === key)?.label || key;
  }

  setRows(rows, metadata = {}) {
    this.rows = Array.isArray(rows) ? [...rows] : [];
    this.metadata = { ...metadata };
    this.renderRows();
  }

  sortedRows() {
    if (!this.sort) return [...this.rows];
    const column = this.columns.find(col => col.key === this.sort.key);
    if (!column) return [...this.rows];
    const factor = this.sort.direction === "desc" ? -1 : 1;
    return this.rows.map((row, index) => ({ row, index })).sort((a, b) => {
      const av = column.sortValue ? column.sortValue(a.row) : a.row[column.key];
      const bv = column.sortValue ? column.sortValue(b.row) : b.row[column.key];
      const aMissing = av === null || av === undefined || av === "";
      const bMissing = bv === null || bv === undefined || bv === "";
      if (aMissing || bMissing) return aMissing === bMissing ? a.index - b.index : aMissing ? 1 : -1;
      return factor * compare(av, bv, column.type) || a.index - b.index;
    }).map(item => item.row);
  }

  renderHead() {
    const row = document.createElement("tr");
    for (const column of this.columns) {
      const th = document.createElement("th");
      th.scope = "col";
      if (column.sortable !== false) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "table-sort";
        button.textContent = column.label;
        if (this.sort?.key === column.key) {
          button.append(` ${this.sort.direction === "asc" ? "↑" : "↓"}`);
          th.setAttribute("aria-sort", this.sort.direction === "asc" ? "ascending" : "descending");
        }
        button.addEventListener("click", () => {
          this.sort = { key: column.key,
            direction: this.sort?.key === column.key && this.sort.direction === "asc" ? "desc" : "asc" };
          this.renderHead();
          this.renderRows();
        });
        th.append(button);
      } else {
        th.textContent = column.label;
      }
      row.append(th);
    }
    this.table.tHead.replaceChildren(row);
  }

  renderRows() {
    const rows = this.sortedRows();
    this.count.textContent = `${rows.length.toLocaleString()} ${rows.length === 1 ? "row" : "rows"}`;
    const fragment = document.createDocumentFragment();
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = this.columns.length;
      cell.className = "table-empty";
      cell.textContent = this.emptyMessage;
      row.append(cell);
      fragment.append(row);
    }
    for (const item of rows) {
      const row = document.createElement("tr");
      for (const column of this.columns) {
        const cell = document.createElement("td");
        const content = column.render ? column.render(item) : item[column.key];
        if (content instanceof Node) cell.append(content);
        else cell.textContent = content === null || content === undefined ? "—" : String(content);
        row.append(cell);
      }
      fragment.append(row);
    }
    this.body.replaceChildren(fragment);
  }
}
