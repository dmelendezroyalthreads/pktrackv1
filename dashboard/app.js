const tableBody = document.querySelector("#orders-table tbody");
const viewFilter = document.getElementById("view-filter");
const searchInput = document.getElementById("search");
const emptyState = document.getElementById("empty-state");
const detail = document.getElementById("order-detail");
const detailTitle = document.getElementById("detail-title");
const detailBody = document.getElementById("detail-body");
const closeDetail = document.getElementById("close-detail");
const syncStatus = document.getElementById("sync-status");
const syncTime = document.getElementById("sync-time");

let allOrders = [];

function statusBadge(order) {
  if (order.order_type === "complete") {
    return '<span class="badge b-complete">Complete</span>';
  }
  if (order.partial_type === "paperwork_only") {
    return '<span class="badge b-paperwork">Paperwork Only</span>';
  }
  return '<span class="badge b-product">Product Only</span>';
}

function yesNo(value) {
  return value
    ? '<span class="yn yes">Yes</span>'
    : '<span class="yn no">No</span>';
}

function applyFilters() {
  const view = viewFilter.value;
  const query = searchInput.value.trim().toLowerCase();

  let rows = allOrders.filter((o) => {
    if (view === "complete" && o.order_type !== "complete") return false;
    if (view === "partial" && o.order_type !== "partial") return false;
    if (view === "paperwork_only" && o.partial_type !== "paperwork_only") return false;
    if (view === "product_only" && o.partial_type !== "product_only") return false;
    return true;
  });

  if (query) {
    rows = rows.filter((o) => {
      const haystack = [
        o.order_key,
        o.prefix,
        o.ref_number,
        o.users_seen,
        o.stages_seen,
        o.latest_added_time,
      ]
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }

  renderRows(rows);
}

function renderRows(rows) {
  tableBody.innerHTML = "";
  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${statusBadge(row)}</td>
      <td>${row.order_key}</td>
      <td>${row.prefix}</td>
      <td>${row.ref_number}</td>
      <td>${yesNo(row.paperwork_received)}</td>
      <td>${yesNo(row.product_received)}</td>
      <td>${row.users_seen || "-"}</td>
      <td>${row.latest_added_time || "-"}</td>
    `;
    tr.addEventListener("click", () => showDetail(row));
    tableBody.appendChild(tr);
  }
  emptyState.classList.toggle("hidden", rows.length > 0);
}

function showDetail(row) {
  detailTitle.textContent = row.order_key;
  detailBody.innerHTML = `
    <dl>
      <dt>Order Type</dt><dd>${row.order_type}</dd>
      <dt>Prefix</dt><dd>${row.prefix || "-"}</dd>
      <dt>Ref Number</dt><dd>${row.ref_number || "-"}</dd>
      <dt>Paperwork Received</dt><dd>${row.paperwork_received ? "Yes" : "No"}</dd>
      <dt>Product Received</dt><dd>${row.product_received ? "Yes" : "No"}</dd>
      <dt>Users Seen</dt><dd>${row.users_seen || "-"}</dd>
      <dt>Stages Seen</dt><dd>${row.stages_seen || "-"}</dd>
      <dt>Latest Added Time</dt><dd>${row.latest_added_time || "-"}</dd>
      <dt>Rows for Order</dt><dd>${row.rows_for_order}</dd>
    </dl>
  `;
  detail.showModal();
}

function setSummary(summary) {
  document.getElementById("count-total").textContent = summary.total_orders_in_view;
  document.getElementById("count-complete").textContent = summary.complete_both;
  document.getElementById("count-partial").textContent = summary.partial_one;
  document.getElementById("count-paperwork-only").textContent = summary.paperwork_only;
  document.getElementById("count-product-only").textContent = summary.product_only;
}

function formatTime(rawIso) {
  if (!rawIso) return "-";
  const d = new Date(rawIso);
  if (Number.isNaN(d.getTime())) return rawIso;
  return d.toLocaleString();
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

async function boot() {
  let payload = null;
  try {
    const live = await fetch("/api/orders", { cache: "no-store" });
    if (live.ok) {
      payload = await live.json();
    }
  } catch (_) {
    // Fall back to static JSON when live API is not running.
  }

  if (!payload) {
    const response = await fetch("./dashboard_data.json", { cache: "no-store" });
    if (!response.ok) {
      throw new Error("Could not load /api/orders or dashboard_data.json");
    }
    payload = await response.json();
  }

  allOrders = payload.orders || [];
  setSummary(payload.summary || {});
  setSyncMeta(payload.meta || {});
  applyFilters();
}

viewFilter.addEventListener("change", applyFilters);
searchInput.addEventListener("input", applyFilters);
closeDetail.addEventListener("click", () => detail.close());

boot().catch((err) => {
  emptyState.textContent = `Failed to load data: ${err.message}`;
  emptyState.classList.remove("hidden");
  syncStatus.textContent = "Live sync: unavailable";
  syncTime.textContent = "Could not reach dashboard API.";
});
