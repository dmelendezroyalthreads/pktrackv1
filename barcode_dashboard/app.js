const tableBody = document.querySelector("#records-table tbody");
const searchInput = document.getElementById("search");
const emptyState = document.getElementById("empty-state");
const syncStatus = document.getElementById("sync-status");
const syncTime = document.getElementById("sync-time");

let allRecords = [];
const emailSubject = "Going to Production and We have the barcodes";

function formatTime(rawIso) {
  if (!rawIso) return "-";
  const d = new Date(rawIso);
  if (Number.isNaN(d.getTime())) return rawIso;
  return d.toLocaleString();
}

function setSummary(summary) {
  document.getElementById("count-total").textContent = summary.total_records ?? 0;
  document.getElementById("count-unique").textContent = summary.unique_orders ?? 0;
}

function setSyncMeta(meta) {
  const last = meta?.last_live_event_at || "";
  if (last) {
    syncStatus.textContent = "Live sync: receiving webhooks";
    syncTime.textContent = `Last webhook: ${formatTime(last)}`;
    return;
  }
  syncStatus.textContent = "Live sync: waiting for first webhook";
  syncTime.textContent = "No live Zoho event has been received yet.";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function emailLink(row) {
  const body = [
    "Team,",
    "",
    "Going to Production and We have the barcodes.",
    "",
    "Record Details:",
    `ORDER / PICK / PO. NUMBER: ${row.order_value || "-"}`,
    `Dropped Off By: ${row.dropped_off_by || "-"}`,
    `Date-Time: ${row.date_time || "-"}`,
    `Added Time: ${row.added_time || "-"}`,
  ].join("\n");

  const url = `https://outlook.office.com/mail/deeplink/compose?subject=${encodeURIComponent(emailSubject)}&body=${encodeURIComponent(body)}`;
  return `<a class="email-link" href="${url}" target="_blank" rel="noopener noreferrer">Email</a>`;
}

function renderRows(rows) {
  tableBody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.id}</td>
      <td>${escapeHtml(row.order_value || "-")}</td>
      <td>${escapeHtml(row.dropped_off_by || "-")}</td>
      <td>${escapeHtml(row.date_time || "-")}</td>
      <td>${escapeHtml(row.added_time || "-")}</td>
      <td>${emailLink(row)}</td>
    `;
    tableBody.appendChild(tr);
  }
  emptyState.classList.toggle("hidden", rows.length > 0);
}

function applySearch() {
  const query = searchInput.value.trim().toLowerCase();
  if (!query) {
    renderRows(allRecords);
    return;
  }

  const rows = allRecords.filter((row) => {
    const haystack = [row.order_value, row.dropped_off_by, row.date_time, row.added_time]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });

  renderRows(rows);
}

async function boot() {
  const response = await fetch("/api/barcode/records", { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Failed to load barcode data (${response.status})`);
  }

  const payload = await response.json();
  allRecords = payload.records || [];
  setSummary(payload.summary || {});
  setSyncMeta(payload.meta || {});
  applySearch();
}

searchInput.addEventListener("input", applySearch);

boot().catch((err) => {
  emptyState.textContent = `Failed to load data: ${err.message}`;
  emptyState.classList.remove("hidden");
  syncStatus.textContent = "Live sync: unavailable";
  syncTime.textContent = "Could not reach barcode API.";
});
