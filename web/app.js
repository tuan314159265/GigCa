const DATA_PATHS = {
  snapshot: "../data/processed/engine_input_snapshot.json",
  weather: "../data/samples/open_meteo_weather_hcmc.json",
  pois: "../data/samples/osm_overpass_pois_hcmc.json",
  route: "../data/samples/osrm_route_hcmc.json",
  registry: "../data/etl/config/source_registry.json",
};

const STATUS_LABELS = {
  available: "Sẵn sàng",
  partial: "Một phần",
  stale: "Đã cũ",
  missing: "Thiếu dữ liệu",
  not_integrated: "Chưa tích hợp",
  insufficient_data: "Chưa đủ dữ liệu",
  live_checked_for_demo: "Đã gọi thử",
  live_checked_prototype_only: "Đã gọi · demo",
  temporarily_unavailable_at_check: "Tạm quá tải",
  timed_out_at_check: "Timeout",
  not_live_checked: "Chưa gọi thử",
  no_machine_readable_api_verified: "Chưa có API xác minh",
};

const OBJECTIVE_LABELS = {
  max_trip_value: "Tối đa giá trị cuốc",
  maintain_position: "Giữ vị trí tốt",
  rest_spot: "Gợi ý điểm chờ / nghỉ",
  safety_comfort: "An toàn · mưa + giao thông",
};

const DATASET_LABELS = {
  weather: "Dự báo mưa",
  poi: "POI khu vực",
  routing: "Routing",
  traffic: "Tình trạng giao thông",
  road_incidents: "Tai nạn / đóng đường",
  verified_waiting_places: "Điểm chờ đã xác minh",
  events: "Sự kiện",
  vehicle_density: "Mật độ xe",
  booking_and_destinations: "Booking / điểm trả khách",
  trip_value: "Giá trị cuốc",
};

const $ = (id) => document.getElementById(id);

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return "—";
  return new Intl.NumberFormat("vi-VN", { maximumFractionDigits: digits }).format(Number(value));
}

function formatDate(value, options = {}) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Ho_Chi_Minh",
    ...options,
  }).format(date);
}

function setStatus(element, status) {
  element.textContent = STATUS_LABELS[status] || status || "Chưa rõ";
  element.className = `status-pill ${status || "missing"}`;
}

function renderSnapshot(snapshot, weatherData, poiData, routeData, registry) {
  const area = snapshot.areas?.[0];
  if (!area) throw new Error("Snapshot chưa có areas[0].");

  $("snapshot-meta").innerHTML = "Snapshot <strong></strong><br>ETL lúc <strong></strong>";
  const metaStrong = $("snapshot-meta").querySelectorAll("strong");
  metaStrong[0].textContent = snapshot.snapshot_id || "—";
  metaStrong[1].textContent = formatDate(snapshot.generated_at);
  $("footer-snapshot").textContent = `${snapshot.snapshot_id || "Snapshot"} · chưa phải khuyến nghị vận hành`;

  const point = area.representative_point || {};
  $("metric-location").textContent = `${formatNumber(point.latitude, 4)}, ${formatNumber(point.longitude, 4)}`;
  $("metric-area").textContent = `${area.area_id || "—"} · ${area.spatial_scope || "—"}`;

  const hours = area.weather?.hourly || [];
  const firstHour = hours[0];
  $("metric-rain").textContent = firstHour?.precipitation_probability_pct == null
    ? "—"
    : `${formatNumber(firstHour.precipitation_probability_pct)}%`;
  $("metric-rain-time").textContent = firstHour ? `Mốc đầu: ${formatDate(firstHour.valid_time)}` : "Không có forecast";

  const poiCounts = area.poi_counts_by_category || {};
  const poiTotal = Object.values(poiCounts).reduce((sum, value) => sum + Number(value || 0), 0);
  $("metric-pois").textContent = formatNumber(poiTotal);
  $("metric-poi-categories").textContent = `${Object.keys(poiCounts).length} nhóm · bán kính ${formatNumber(poiData.coverage?.radius_m)} m`;

  const route = (routeData.response?.routes || [])[0] || {};
  $("metric-route").textContent = `${(Number(route.distance || 0) / 1000).toFixed(2)} km`;
  $("metric-route-time").textContent = `${formatNumber(Number(route.duration || 0) / 60, 1)} phút theo API`;
  $("route-profile").textContent = routeData.request?.profile || routeData.source?.profile || "—";
  $("route-distance").textContent = `${formatNumber(route.distance, 1)} m`;
  $("route-duration").textContent = `${formatNumber(Number(route.duration || 0) / 60, 1)} phút`;
  $("route-origin").textContent = coordinateText(routeData.request?.origin);
  $("route-destination").textContent = coordinateText(routeData.request?.destination);

  const weatherStatus = snapshot.data_status?.find((item) => item.dataset === "weather")?.status || "missing";
  setStatus($("weather-status"), weatherStatus);
  if (weatherStatus === "stale") {
    $("stale-banner").hidden = false;
    const reason = snapshot.data_status.find((item) => item.dataset === "weather")?.reason;
    $("stale-message").textContent = `${reason || "Forecast đã hết hạn."} Chạy ETL với dữ liệu mới trước khi dùng cho quyết định hiện tại.`;
  }
  const providerGrid = area.weather?.provider_grid_location;
  if (providerGrid) {
    $("weather-location-note").textContent = `Grid Open-Meteo: ${formatNumber(providerGrid.latitude, 4)}, ${formatNumber(providerGrid.longitude, 4)}. Đây là dự báo, không phải đo mưa tại từng tuyến đường.`;
  }
  renderWeather(hours);
  renderReadiness(snapshot);
  renderPoiBreakdown(poiCounts);
  renderPoiList(poiData.pois || []);
  renderSources(registry);
}

function coordinateText(point) {
  if (!point) return "—";
  return `${formatNumber(point.latitude, 5)}, ${formatNumber(point.longitude, 5)}`;
}

function renderWeather(hours) {
  const chart = $("weather-chart");
  const axis = $("weather-axis");
  chart.replaceChildren();
  axis.replaceChildren();
  if (!hours.length) {
    chart.append(node("div", "empty-state", "Snapshot không có dữ liệu theo giờ."));
    return;
  }
  const values = hours.map((hour) => Number(hour.precipitation_probability_pct) || 0);
  const maximum = Math.max(100, ...values);
  hours.forEach((hour, index) => {
    const wrap = node("div", "rain-bar-wrap");
    const bar = node("div", "rain-bar");
    const probability = hour.precipitation_probability_pct;
    const height = probability == null ? 2 : Math.max(3, (Number(probability) / maximum) * 100);
    bar.style.height = `${height}%`;
    wrap.title = `${formatDate(hour.valid_time)} · Xác suất mưa ${probability == null ? "không có" : `${probability}%`} · Lượng mưa ${hour.precipitation_mm == null ? "không có" : `${hour.precipitation_mm} mm`}`;
    wrap.setAttribute("aria-label", wrap.title);
    wrap.append(bar);
    chart.append(wrap);
  });
  const first = new Date(hours[0].valid_time);
  const last = new Date(hours[hours.length - 1].valid_time);
  axis.append(node("span", "", formatDate(first, { dateStyle: "short", timeStyle: "short" })));
  axis.append(node("span", "", `${hours.length} giờ`));
  axis.append(node("span", "", formatDate(last, { dateStyle: "short", timeStyle: "short" })));
}

function renderReadiness(snapshot) {
  const container = $("readiness-list");
  container.replaceChildren();
  const items = snapshot.objective_readiness || [];
  $("readiness-count").textContent = `${items.length} mục tiêu`;
  items.forEach((item) => {
    const row = node("div", "readiness-row");
    const title = node("span", "readiness-name", OBJECTIVE_LABELS[item.objective] || item.objective);
    const status = node("span", `status-tag ${item.status}`, STATUS_LABELS[item.status] || item.status);
    const reason = node("span", "readiness-reason", item.reason || "Chưa có mô tả.");
    row.append(title, status, reason);
    if (item.blocking_datasets?.length) {
      const blockers = item.blocking_datasets
        .map((dataset) => DATASET_LABELS[dataset] || dataset)
        .join(" · ");
      row.append(node("span", "readiness-blockers", `Cần bổ sung: ${blockers}`));
    }
    container.append(row);
  });
}

function renderPoiBreakdown(counts) {
  const container = $("poi-breakdown");
  container.replaceChildren();
  const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 8);
  const max = Math.max(1, ...entries.map((entry) => Number(entry[1])));
  entries.forEach(([category, count]) => {
    const item = node("div", "poi-category");
    const top = node("div", "poi-category-top");
    top.append(node("span", "", category), node("strong", "", formatNumber(count)));
    const track = node("div", "mini-track");
    const fill = node("div", "mini-fill");
    fill.style.width = `${(Number(count) / max) * 100}%`;
    track.append(fill);
    item.append(top, track);
    container.append(item);
  });
}

let allPois = [];
function renderPoiList(pois) {
  allPois = pois;
  const search = $("poi-search");
  const list = $("poi-list");
  const query = (search.value || "").trim().toLocaleLowerCase("vi");
  const filtered = allPois.filter((poi) => [poi.name, poi.category, poi.subcategory]
    .some((value) => String(value || "").toLocaleLowerCase("vi").includes(query)));
  list.replaceChildren();
  $("poi-result-count").textContent = `${formatNumber(filtered.length)} kết quả`;
  filtered.slice(0, 24).forEach((poi) => {
    const item = node("div", "poi-item");
    const pin = node("span", "poi-pin", "⌖");
    const text = node("div", "poi-text");
    const name = node("span", "poi-name", poi.name || `${poi.category || "POI"} · ${poi.osm_type || "OSM"} ${poi.osm_id || ""}`);
    const meta = node("span", "poi-meta", `${poi.category || "other"}${poi.subcategory ? ` / ${poi.subcategory}` : ""} · ${coordinateText(poi)}`);
    text.append(name, meta);
    item.append(pin, text);
    list.append(item);
  });
  if (!filtered.length) list.append(node("div", "empty-state", "Không tìm thấy POI phù hợp."));
  if (filtered.length > 24) list.append(node("div", "empty-state", `Đang hiển thị 24 / ${formatNumber(filtered.length)} kết quả.`));
}

function prettyStatus(value) {
  return STATUS_LABELS[value] || String(value || "Chưa rõ").replaceAll("_", " ");
}

function sourceCard(provider, status, notes) {
  const card = node("article", "source-card");
  const top = node("div", "source-card-top");
  top.append(node("span", "source-name", provider));
  top.append(node("span", `source-state ${status}`, prettyStatus(status)));
  card.append(top, node("p", "source-note", notes || "Không có ghi chú."));
  return card;
}

function renderSources(registry) {
  const grid = $("source-grid");
  grid.replaceChildren();
  for (const [dataset, config] of Object.entries(registry.datasets || {})) {
    const selected = config.primary;
    if (selected) grid.append(sourceCard(`${DATASET_LABELS[dataset] || dataset} · ${selected.provider}`, selected.status, selected.notes));
    for (const candidate of [...(config.fallbacks || []), ...(config.candidates || [])]) {
      grid.append(sourceCard(`${DATASET_LABELS[dataset] || dataset} · ${candidate.provider}`, candidate.status, candidate.notes));
    }
    if (!selected && !(config.candidates || []).length && !(config.fallbacks || []).length) {
      grid.append(sourceCard(DATASET_LABELS[dataset] || dataset, "missing", "Chưa cấu hình nhà cung cấp."));
    }
  }
}

async function loadDashboard() {
  $("load-error").hidden = true;
  try {
    const responses = await Promise.all(Object.values(DATA_PATHS).map((path) => fetch(path, { cache: "no-store" })));
    const failedIndex = responses.findIndex((response) => !response.ok);
    if (failedIndex !== -1) {
      const failedPath = Object.keys(DATA_PATHS)[failedIndex];
      throw new Error(`Không đọc được ${failedPath} (${responses[failedIndex].status}). Hãy chạy ETL trước.`);
    }
    const [snapshot, weather, pois, route, registry] = await Promise.all(responses.map((response) => response.json()));
    $("poi-radius").textContent = `Bán kính ${formatNumber(pois.coverage?.radius_m)} m`;
    renderSnapshot(snapshot, weather, pois, route, registry);
  } catch (error) {
    const box = $("load-error");
    box.hidden = false;
    box.replaceChildren(
      node("strong", "", "Chưa tải được dữ liệu."),
      node("div", "", `${error.message} Chạy web từ thư mục repo để trình duyệt đọc được JSON:`),
      node("code", "", ".venv/bin/python -m http.server 8000"),
      node("div", "", "Sau đó mở http://localhost:8000/web/ . Nếu snapshot chưa có, chạy .venv/bin/python -m data.etl.pipeline trước."),
    );
  }
}

$("reload-button").addEventListener("click", loadDashboard);
$("poi-search").addEventListener("input", () => renderPoiList(allPois));
loadDashboard();
