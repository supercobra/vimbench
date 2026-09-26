const body = document.querySelector("#leaderboard-body");
const modelCount = document.querySelector("#model-count");

const percent = (value) => `${(value * 100).toFixed(1).replace(".0", "")}%`;
const decimal = (value) => Number(value).toFixed(3);

function renderRows(rows) {
  modelCount.textContent = rows.length;
  body.replaceChildren(
    ...rows.map((row, index) => {
      const tr = document.createElement("tr");
      const cells = [
        { className: "rank", text: String(index + 1).padStart(2, "0") },
        { className: "model", text: row.model },
        { className: "pass-cell" },
        { text: `${row.passed} / ${row.tasks}` },
        { text: decimal(row.avg_efficiency) },
        { text: decimal(row.avg_partial) },
        { text: `${Number(row.seconds).toFixed(1)}s` },
      ];

      cells.forEach((cell, cellIndex) => {
        const td = document.createElement("td");
        if (cell.className) td.className = cell.className;
        if (cell.text) td.textContent = cell.text;

        if (cellIndex === 1 && index === 0) {
          const badge = document.createElement("span");
          badge.className = "badge";
          badge.textContent = "TOP";
          td.append(badge);
        }

        if (cellIndex === 2) {
          const value = document.createElement("span");
          value.className = "pass-value";
          value.textContent = percent(row.pass_rate);
          const bar = document.createElement("span");
          bar.className = "bar";
          bar.setAttribute("aria-hidden", "true");
          const fill = document.createElement("i");
          fill.style.width = `${row.pass_rate * 100}%`;
          bar.append(fill);
          td.append(value, bar);
          td.setAttribute("aria-label", `${percent(row.pass_rate)} pass rate`);
        }
        tr.append(td);
      });
      return tr;
    }),
  );
}

fetch("data/leaderboard.json")
  .then((response) => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then((payload) => renderRows(payload.rows))
  .catch((error) => {
    body.innerHTML = `<tr><td colspan="7" class="loading">Results could not be loaded (${error.message}). View the raw data on GitHub.</td></tr>`;
  });
