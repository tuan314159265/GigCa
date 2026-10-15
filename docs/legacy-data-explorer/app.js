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

async function renderDatabaseDiagram() {
  const status = $('database-diagram-status');
  const container = $('database-diagram');
  try {
    const response = await fetch('../docs/07_DATABASE_DESIGN.md', { cache: 'no-store' });
    if (!response.ok) throw new Error(`Không đọc được tài liệu DB (HTTP ${response.status}).`);
    const markdown = await response.text();
    const match = markdown.match(/```mermaid\s*([\s\S]*?)```/i);
    if (!match) throw new Error('Tài liệu DB chưa có khối Mermaid.');
    if (!window.mermaid) throw new Error('Không tải được Mermaid; kiểm tra kết nối CDN.');

    window.mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: 'neutral' });
    const rendered = await window.mermaid.render('gigca-database-erd', match[1].trim());
    container.innerHTML = rendered.svg;
    rendered.bindFunctions?.(container);
    status.textContent = 'Sơ đồ lấy từ docs/07_DATABASE_DESIGN.md · quan hệ theo khóa ngoại trong migrations.';
    status.className = 'diagram-status available';
  } catch (error) {
    status.textContent = `${error.message} Mở tài liệu thiết kế để xem mã Mermaid.`;
    status.className = 'diagram-status partial';
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

let liveMap;
let pickMode = null;
let liveOrigin = { latitude: 10.7769, longitude: 106.7009 };
let liveDestination = { latitude: 10.7796, longitude: 106.6932 };
let liveRouteLayer;
let liveLayers;
let layerRefreshTimer;
let lastLayerCenter;

function apiUrl(path, parameters = {}) {
  const query = new URLSearchParams(parameters);
  return `/api/${path}${query.size ? `?${query}` : ''}`;
}

async function getApiJson(path, parameters = {}) {
  const response = await fetch(apiUrl(path, parameters), { cache: 'no-store' });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `${path}: HTTP ${response.status}`);
  return payload;
}

function escapeHtml(value) {
  return String(value || '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  })[character]);
}

function addObservation(icon, title, detail) {
  const row = node('div', 'live-observation');
  row.append(node('span', 'live-observation-icon', icon));
  const body = node('div');
  body.append(node('strong', '', title), node('small', '', detail));
  row.append(body);
  $('live-observations').append(row);
}

function setMapStatus(status, label) {
  $('map-status').className = `status-pill ${status}`;
  $('map-status').textContent = label;
}

function updateMapPointLabels() {
  $('map-origin').textContent = coordinateText(liveOrigin);
  $('map-destination').textContent = coordinateText(liveDestination);
}

function iconMarker(text, className) {
  const size = className === 'rain-map-icon' ? 38 : 25;
  return L.divIcon({ className: '', html: `<div class="${className}"><span>${escapeHtml(text)}</span></div>`, iconSize: [size, size], iconAnchor: [size / 2, size - 2] });
}

function renderLivePois(data) {
  liveLayers.pois.clearLayers();
  (data.pois || []).forEach((poi) => {
    L.marker([poi.latitude, poi.longitude], { icon: iconMarker('P', 'map-pin') })
      .bindPopup(`<strong>${escapeHtml(poi.name || 'POI')}</strong><br>${escapeHtml(poi.category || 'POI')} · ${escapeHtml(poi.address || '')}`)
      .addTo(liveLayers.pois);
  });
  addObservation('P', 'POI quán cà phê', `${formatNumber((data.pois || []).length)} kết quả trong bán kính ${formatNumber(data.radius_m)} m · TomTom Search`);
}

function renderLiveTraffic(data) {
  liveLayers.traffic.clearLayers();
  const flow = data.flow || {};
  const coordinates = flow.coordinates?.coordinate || [];
  if (coordinates.length > 1) {
    const ratio = Number(flow.currentSpeed) / Math.max(1, Number(flow.freeFlowSpeed));
    const color = ratio < 0.4 ? '#bd4a43' : ratio < 0.7 ? '#dc9b32' : '#298b70';
    L.polyline(coordinates.map((point) => [point.latitude, point.longitude]), { color, weight: 6, opacity: 0.9 })
      .bindPopup(`Traffic TomTom<br>${formatNumber(flow.currentSpeed)} / ${formatNumber(flow.freeFlowSpeed)} km/h · confidence ${formatNumber(flow.confidence, 2)}`)
      .addTo(liveLayers.traffic);
  }
  const incidents = data.incidents || [];
  incidents.forEach((incident) => {
    const geometry = incident.geometry || {};
    const properties = incident.properties || {};
    const description = properties.events?.[0]?.description || 'Sự cố giao thông';
    const coords = geometry.coordinates || [];
    const label = [properties.from, properties.to].filter(Boolean).join(' → ');
    if (geometry.type === 'LineString' && coords.length > 1) {
      L.polyline(coords.map(([lon, lat]) => [lat, lon]), { color: '#c84e47', weight: 4, opacity: 0.82, dashArray: '5 5' })
        .bindPopup(`<strong>${escapeHtml(description)}</strong><br>${escapeHtml(label)}<br>Trễ ${formatNumber(properties.delay)} giây`)
        .addTo(liveLayers.traffic);
    } else if (geometry.type === 'Point' && coords.length > 1) {
      L.marker([coords[1], coords[0]], { icon: iconMarker('!', 'traffic-incident-icon') })
        .bindPopup(`<strong>${escapeHtml(description)}</strong><br>${escapeHtml(label)}`)
        .addTo(liveLayers.traffic);
    }
  });
  addObservation('↗', 'Lưu lượng trên đoạn gần tâm bản đồ', `${formatNumber(flow.currentSpeed)} km/h · thông thoáng ${formatNumber(flow.freeFlowSpeed)} km/h · confidence ${formatNumber(flow.confidence, 2)}`);
  addObservation('!', 'Sự cố trong vùng lấy mẫu', `${formatNumber(incidents.length)} sự kiện · TomTom tại thời điểm gọi`);
}

function renderLiveWeather(data) {
  liveLayers.rain.clearLayers();
  const now = Date.now();
  const hourly = data.hourly || [];
  const observation = hourly.find((entry) => new Date(entry.valid_time).getTime() >= now) || hourly[0];
  if (!observation) throw new Error('Chưa có forecast mưa được cập nhật theo lịch trong database.');
  const chance = observation.precipitation_probability_pct;
  const location = data.provider_location || data.requested_location;
  L.marker([location.latitude, location.longitude], { icon: iconMarker(chance == null ? '?' : `${Math.round(chance)}%`, 'rain-map-icon') })
    .bindPopup(`Forecast mưa · ${chance == null ? 'không có xác suất' : `${chance}%`}<br>${formatNumber(observation.precipitation_mm, 1)} mm · ${formatDate(observation.valid_time)}`)
    .addTo(liveLayers.rain);
  const freshness = data.data_status === 'stale' ? ` · dữ liệu cũ từ ${formatDate(data.fetched_at)}` : ` · cập nhật ${formatDate(data.fetched_at)}`;
  addObservation('☂', 'Xác suất mưa tại tọa độ này', `${chance == null ? 'Chưa có' : `${formatNumber(chance)}%`} · ${formatNumber(observation.precipitation_mm, 1)} mm · ${formatDate(observation.valid_time)}${freshness}`);
}

async function loadSpatialPoiLayers() {
  const [gridResponse, candidatesResponse, tomtomCandidatesResponse] = await Promise.allSettled([
    fetch('../data/samples/osm_poi_grid_hcmc.json', { cache: 'no-store' }),
    fetch('../data/samples/osm_waiting_candidates_hcmc.json', { cache: 'no-store' }),
    fetch('../data/raw/tomtom_search/tomtom_waiting_candidates_hcmc.json', { cache: 'no-store' }),
  ]);
  if (gridResponse.status === 'fulfilled' && gridResponse.value.ok) {
    const data = await gridResponse.value.json();
    const cells = data.cells || [];
    const maxDensity = Math.max(1, ...cells.map((cell) => Number(cell.cafe_density_per_km2 || 0)));
    cells.forEach((cell) => {
      const count = Number(cell.cafe_poi_count || 0);
      const strength = Number(cell.cafe_density_per_km2 || 0) / maxDensity;
      const color = strength > 0.66 ? '#b95545' : strength > 0.33 ? '#dc9a39' : '#55a58c';
      const nearbyCount = cell.cafe_poi_count_within_500m == null ? 'chưa đủ coverage' : `${formatNumber(cell.cafe_poi_count_within_500m)} quán`;
      L.geoJSON(cell.geometry, { style: { color, weight: 1, fillColor: color, fillOpacity: 0.12 + strength * 0.35 } })
        .bindPopup(`<strong>${escapeHtml(cell.cell_id)}</strong><br>${formatNumber(count)} cafe trong ô · ${formatNumber(cell.cafe_density_per_km2, 1)} quán/km²<br>${nearbyCount} trong bán kính 500 m`)
        .addTo(liveLayers.cafeGrid);
    });
    if ($('layer-cafe-grid').checked) liveLayers.cafeGrid.addTo(liveMap);
  }
  if (candidatesResponse.status === 'fulfilled' && candidatesResponse.value.ok) {
    const data = await candidatesResponse.value.json();
    let candidates = data.candidates || [];
    if (tomtomCandidatesResponse.status === 'fulfilled' && tomtomCandidatesResponse.value.ok) {
      const tomtom = await tomtomCandidatesResponse.value.json();
      candidates = candidates.concat(tomtom.candidates || []);
    }
    const symbols = { parking: 'P', church: 'H', place_of_worship: 'H', school: 'S', shopping_center: 'M', open_land: 'O', park: 'G', fuel_station: 'F', transit_or_rest_area: 'T' };
    candidates.forEach((candidate) => {
      const label = candidate.name || candidate.poi_type;
      const marker = L.marker([candidate.latitude, candidate.longitude], {
        icon: iconMarker(symbols[candidate.poi_type] || '?', 'candidate-map-icon'),
      });
      marker.bindPopup(`<strong>${escapeHtml(label)}</strong><br>${escapeHtml(candidate.poi_type)} · ứng viên chưa xác minh<br>Quyền vào/chờ: chưa rõ${candidate.area_m2 ? `<br>Diện tích OSM xấp xỉ: ${formatNumber(candidate.area_m2)} m²` : ''}`);
      marker.addTo(liveLayers.waitCandidates);
    });
    addObservation('⌖', 'Ứng viên điểm chờ chưa xác minh', `${formatNumber(candidates.length)} POI từ OSM + TomTom; quyền vào/chờ vẫn chưa rõ.`);
    if ($('layer-wait-candidates').checked) liveLayers.waitCandidates.addTo(liveMap);
  }
}

async function refreshLiveLayers() {
  if (!liveMap) return;
  $('live-observations').replaceChildren();
  setMapStatus('partial', 'Đang tải dữ liệu live…');
  const center = liveMap.getCenter();
  lastLayerCenter = { latitude: center.lat, longitude: center.lng };
  const pointParams = { lat: center.lat.toFixed(5), lon: center.lng.toFixed(5) };
  const results = await Promise.allSettled([
    getApiJson('pois', { ...pointParams, radius: 1500, query: 'cafe' }),
    getApiJson('traffic', { ...pointParams, radius: 1500 }),
    getApiJson('weather', pointParams),
  ]);
  const errors = [];
  const [pois, traffic, weather] = results;
  if (pois.status === 'fulfilled') {
    renderLivePois(pois.value);
    if ($('layer-pois').checked) liveLayers.pois.addTo(liveMap);
    else liveMap.removeLayer(liveLayers.pois);
  } else errors.push(`POI: ${pois.reason.message}`);
  if (traffic.status === 'fulfilled') {
    renderLiveTraffic(traffic.value);
    if ($('layer-traffic').checked) liveLayers.traffic.addTo(liveMap);
    else liveMap.removeLayer(liveLayers.traffic);
  } else errors.push(`Traffic: ${traffic.reason.message}`);
  if (weather.status === 'fulfilled') {
    renderLiveWeather(weather.value);
    if ($('layer-rain').checked) liveLayers.rain.addTo(liveMap);
    else liveMap.removeLayer(liveLayers.rain);
  } else errors.push(`Mưa: ${weather.reason.message}`);
  const completed = results.filter((result) => result.status === 'fulfilled').length;
  const weatherStale = weather.status === 'fulfilled' && weather.value.data_status === 'stale';
  setMapStatus(completed === 3 && !weatherStale ? 'available' : 'partial',
    `${completed}/3 nguồn${weatherStale ? ' · forecast mưa stale' : ' · mưa theo lịch'}`);
  $('map-updated').textContent = `Cập nhật ${formatDate(new Date().toISOString())}`;
  if (errors.length) addObservation('!', 'Một số nguồn chưa tải được', errors.join(' · '));
}

async function calculateLiveRoute() {
  if (!liveMap) return;
  const button = $('calculate-route');
  button.disabled = true;
  button.textContent = 'Đang tính tuyến…';
  $('map-route-summary').textContent = 'Đang gọi TomTom…';
  try {
    const data = await getApiJson('route', {
      origin_lat: liveOrigin.latitude,
      origin_lon: liveOrigin.longitude,
      destination_lat: liveDestination.latitude,
      destination_lon: liveDestination.longitude,
    });
    const route = data.route;
    const points = route.legs?.[0]?.points || [];
    if (!points.length) throw new Error('API không trả hình học tuyến.');
    const latLngs = points.map((point) => [point.latitude, point.longitude]);
    if (liveRouteLayer) liveMap.removeLayer(liveRouteLayer);
    liveRouteLayer = L.polyline(latLngs, { color: '#176fbd', weight: 5, opacity: 0.9 }).addTo(liveMap);
    const summary = route.summary || {};
    $('map-route-summary').textContent = `${(Number(summary.lengthInMeters || 0) / 1000).toFixed(2)} km · ${(Number(summary.travelTimeInSeconds || 0) / 60).toFixed(1)} phút`;
    $('map-route-detail').textContent = `TomTom Routing · motorcycle · delay ${summary.trafficDelayInSeconds ?? 0}s · ${formatDate(data.fetched_at)}`;
    liveMap.fitBounds(liveRouteLayer.getBounds().pad(0.15));
  } catch (error) {
    $('map-route-summary').textContent = 'Chưa tính được tuyến';
    $('map-route-detail').textContent = error.message;
  } finally {
    button.disabled = false;
    button.textContent = 'Tính tuyến xe máy';
  }
}

function initLiveMap() {
  if (!window.L) {
    setMapStatus('missing', 'Không tải được thư viện bản đồ');
    $('live-observations').replaceChildren(node('div', 'empty-state', 'Kiểm tra kết nối tới unpkg.com để tải Leaflet.'));
    return;
  }
  liveMap = L.map('gigca-map', { zoomControl: true }).setView([10.7769, 106.7009], 14);
  L.tileLayer('/api/map/tiles/{z}/{x}/{y}.png', { minZoom: 0, maxZoom: 22, attribution: '© TomTom', crossOrigin: true }).addTo(liveMap);
  liveLayers = { pois: L.layerGroup(), cafeGrid: L.layerGroup(), waitCandidates: L.layerGroup(), traffic: L.layerGroup(), rain: L.layerGroup() };
  updateMapPointLabels();
  liveMap.on('click', (event) => {
    if (!pickMode) return;
    const chosen = { latitude: event.latlng.lat, longitude: event.latlng.lng };
    const selectedMode = pickMode;
    if (selectedMode === 'origin') liveOrigin = chosen;
    else liveDestination = chosen;
    pickMode = null;
    $('pick-origin').classList.remove('active');
    $('pick-destination').classList.remove('active');
    liveMap.getContainer().style.cursor = '';
    updateMapPointLabels();
    L.popup().setLatLng(event.latlng).setContent(`Đã đặt ${selectedMode === 'origin' ? 'điểm đi' : 'điểm đến'}.`).openOn(liveMap);
  });
  liveMap.on('moveend', () => {
    if (!lastLayerCenter) return;
    const center = liveMap.getCenter();
    if (Math.abs(center.lat - lastLayerCenter.latitude) < 0.01 && Math.abs(center.lng - lastLayerCenter.longitude) < 0.01) return;
    clearTimeout(layerRefreshTimer);
    layerRefreshTimer = setTimeout(refreshLiveLayers, 650);
  });
  $('pick-origin').addEventListener('click', () => {
    pickMode = 'origin';
    $('pick-origin').classList.add('active');
    $('pick-destination').classList.remove('active');
    liveMap.getContainer().style.cursor = 'crosshair';
  });
  $('pick-destination').addEventListener('click', () => {
    pickMode = 'destination';
    $('pick-destination').classList.add('active');
    $('pick-origin').classList.remove('active');
    liveMap.getContainer().style.cursor = 'crosshair';
  });
  $('calculate-route').addEventListener('click', calculateLiveRoute);
  for (const [inputId, layer] of [['layer-pois', liveLayers.pois], ['layer-cafe-grid', liveLayers.cafeGrid], ['layer-wait-candidates', liveLayers.waitCandidates], ['layer-traffic', liveLayers.traffic], ['layer-rain', liveLayers.rain]]) {
    $(inputId).addEventListener('change', (event) => {
      if (event.target.checked) layer.addTo(liveMap);
      else liveMap.removeLayer(layer);
    });
  }
  loadSpatialPoiLayers().catch((error) => addObservation('!', 'Không tải được lớp POI mẫu', error.message));
  refreshLiveLayers();
  calculateLiveRoute();
}

$("reload-button").addEventListener("click", () => {
  loadDashboard();
  refreshLiveLayers();
});
$("poi-search").addEventListener("input", () => renderPoiList(allPois));
loadDashboard();
renderDatabaseDiagram();
initLiveMap();
