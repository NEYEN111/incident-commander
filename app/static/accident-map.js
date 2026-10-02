/* Leaflet 1.9.4 + Leaflet.markercluster 1.5.3, both vendored under /static/vendor. */
(() => {
  "use strict";
  const status = document.getElementById("map-status");
  const error = document.getElementById("map-error");
  const filters = document.getElementById("map-filters");
  if (typeof L === "undefined" || typeof L.markerClusterGroup !== "function") {
    status.textContent = "No se pudo cargar el mapa. Recarga la página.";
    return;
  }
  const map = L.map("accident-map").setView([20, 0], 2);
  const tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  tiles.on("tileerror", () => {
    error.hidden = false;
    error.textContent = "No se pudo cargar parte del mapa base de OpenStreetMap. Revisa la conexión.";
  });
  const clusterOptions = {
    showCoverageOnHover: false, spiderfyOnMaxZoom: true, chunkedLoading: true,
  };
  let clusters = L.markerClusterGroup(clusterOptions).addTo(map);
  const zones = {1: "Urbana", 2: "Rural", 3: "No determinada"};
  const colors = {Fatal: "fatal", Grave: "grave", Leve: "leve"};
  let pending;

  function popup(accident) {
    const box = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = accident.title || `Accidente ${accident.id}`;
    box.append(title);
    function line(label, value) {
      const text = document.createElement("p");
      text.textContent = `${label}: ${value}`;
      box.append(text);
    }
    line("Fecha", accident.date ? accident.date.split("-").reverse().join("/") : "Sin datos");
    line("Hora", accident.time || "Sin datos");
    line("Zona", zones[accident.urban_or_rural_area] || "Sin datos");
    const latest = accident.latest_prediction;
    line("Última predicción ML", latest ? latest.prediction : "Sin predicción");
    if (latest) {
      const probabilities = latest.probabilities;
      line("Probabilidades estimadas", ["Fatal", "Grave", "Leve"]
        .map(name => `${name} ${(probabilities[name] * 100).toFixed(1)}%`).join(" · "));
    }
    const link = document.createElement("a");
    link.href = `/incidents/${encodeURIComponent(accident.id)}`;
    link.textContent = "Ver accidente";
    box.append(link);
    return box;
  }

  async function load() {
    if (pending) pending.abort();
    const request = new AbortController();
    pending = request;
    const params = new URLSearchParams();
    for (const [name, value] of new FormData(filters)) {
      if (value !== "") params.set(name, value);
    }
    status.textContent = "Cargando accidentes…";
    error.hidden = true;
    try {
      const response = await fetch(`/maps/incidents.json?${params}`, {
        signal: request.signal, headers: {Accept: "application/json"},
      });
      if (response.redirected) {
        window.location.assign(response.url);
        return;
      }
      if (!response.ok) {
        const body = await response.json();
        throw new Error(typeof body.detail === "string" ? body.detail : "Revisa los filtros seleccionados.");
      }
      const data = await response.json();
      if (pending !== request) return;
      const markers = data.incidents.map(accident => {
        const severity = accident.latest_prediction?.prediction;
        const icon = L.divIcon({
          className: `accident-marker ${colors[severity] || "neutral"}`,
          html: '<span aria-hidden="true"></span>', iconSize: [22, 22], iconAnchor: [11, 11],
        });
        return L.marker([accident.latitude, accident.longitude], {icon})
          .bindPopup(popup(accident));
      });
      map.removeLayer(clusters);
      clusters = L.markerClusterGroup(clusterOptions).addTo(map);
      clusters.addLayers(markers);
      if (markers.length) {
        map.fitBounds(L.latLngBounds(markers.map(marker => marker.getLatLng())), {
          padding: [25, 25], maxZoom: 16,
        });
      }
      status.textContent = `${data.count} ${data.count === 1 ? "accidente encontrado" : "accidentes encontrados"}`;
    } catch (failure) {
      if (failure.name === "AbortError" || pending !== request) return;
      clusters.clearLayers();
      status.textContent = "No se pudieron cargar los accidentes.";
      error.hidden = false;
      error.textContent = failure.message;
    }
  }
  filters.addEventListener("submit", event => { event.preventDefault(); load(); });
  filters.addEventListener("change", load);
  filters.addEventListener("reset", () => setTimeout(load, 0));
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("accident-map"));
  load();
})();
