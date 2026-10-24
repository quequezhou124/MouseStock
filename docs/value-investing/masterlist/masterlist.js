const search = document.getElementById("stock-search");
const count = document.getElementById("result-count");
const list = document.getElementById("stock-list");
const empty = document.getElementById("empty-state");
const more = document.getElementById("load-more");

const pageSize = 100;
let stocks = [];
let matches = [];
let shown = 0;

function appendPage() {
  const next = matches.slice(shown, shown + pageSize);
  const fragment = document.createDocumentFragment();
  for (const name of next) {
    const item = document.createElement("li");
    item.textContent = name;
    fragment.appendChild(item);
  }
  list.appendChild(fragment);
  shown += next.length;
  more.hidden = shown >= matches.length;
}

function render() {
  const query = search.value.trim().toLocaleLowerCase();
  matches = query ? stocks.filter(name => name.toLocaleLowerCase().includes(query)) : stocks;
  shown = 0;
  list.replaceChildren();
  empty.hidden = matches.length !== 0;
  count.textContent = `${matches.length.toLocaleString()} ${matches.length === 1 ? "stock" : "stocks"}${query ? " found" : " in the masterlist"}`;
  appendPage();
}

search.addEventListener("input", render);
more.addEventListener("click", appendPage);

fetch("stocks.json")
  .then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(data => {
    if (!Array.isArray(data)) throw new Error("Invalid stock data");
    stocks = data;
    render();
  })
  .catch(() => {
    count.textContent = "The masterlist could not be loaded. Please refresh the page.";
    more.hidden = true;
  });
