/* Leaflet 1.9.4 + Leaflet.markercluster 1.5.3, both vendored under /static/vendor. */
(() => {
  "use strict";
  const status = document.getElementById("map-status");
  const error = document.getElementById("map-error");
  const empty = document.getElementById("map-empty");
  const filters = document.getElementById("map-filters");
  if (typeof L === "undefined" || typeof L.markerClusterGroup !== "function") {
    status.textContent = "No se pudo cargar el mapa. Recarga la página.";
    return;
  }
  const map = L.map("accident-map", {
    zoomAnimation: false, fadeAnimation: false, markerZoomAnimation: false,
  }).setView([20, 0], 2);
  map.zoomControl.setPosition("topleft");
  const zoomButtons = document.querySelectorAll("#accident-map .leaflet-control-zoom a");
  ["Acercar", "Alejar"].forEach((label, index) => {
    zoomButtons[index].setAttribute("aria-label", label);
    zoomButtons[index].setAttribute("title", label);
  });
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
    animate: false,
    iconCreateFunction(cluster) {
      const count = cluster.getChildCount();
      return L.divIcon({
        className: "map-cluster", iconSize: [44, 44], iconAnchor: [22, 22],
        html: `<span role="img" aria-label="${count} accidentes agrupados">${count}</span>`,
      });
    },
  };
  let clusters = L.markerClusterGroup(clusterOptions).addTo(map);
  const zones = {1: "Urbana", 2: "Rural", 3: "No determinada"};
  // Match the existing ui_es labels without changing stored or API status values.
  const statusLabels = {
    Triage: "Pendiente", Investigating: "En atención", Identified: "Identificado",
    Monitoring: "En seguimiento", Closed: "Cerrado",
  };
  const colors = {Fatal: "fatal", Grave: "grave", Leve: "leve"};
  const symbols = {Fatal: "F", Grave: "G", Leve: "L"};
  let pending;

  function popup(accident) {
    const box = document.createElement("div");
    box.className = "map-popup";
    const title = document.createElement("h2");
    title.className = "map-popup-title";
    title.textContent = accident.title || `Accidente ${accident.id}`;
    box.append(title);
    const facts = document.createElement("dl");
    function line(label, value) {
      const term = document.createElement("dt"), text = document.createElement("dd");
      term.textContent = label;
      text.textContent = value;
      facts.append(term, text);
    }
    line("Fecha", accident.date ? accident.date.split("-").reverse().join("/") : "Sin datos");
    line("Hora", accident.time || "Sin datos");
    line("Zona", zones[accident.urban_or_rural_area] || "Sin datos");
    line("Prioridad de atención", accident.operational_priority_label || accident.operational_priority || "Sin asignar");
    line("Estado", Object.hasOwn(statusLabels, accident.status)
      ? statusLabels[accident.status] : accident.status || "Sin datos");
    box.append(facts);
    const latest = accident.latest_prediction;
    const result = document.createElement("p"), label = document.createElement("span");
    result.className = "map-popup-result";
    result.append(document.createTextNode("Gravedad estimada: "));
    label.className = `map-popup-severity ${colors[latest?.prediction] || "neutral"}`;
    label.textContent = latest ? latest.prediction : "Sin análisis ML";
    result.append(label);
    box.append(result);
    if (latest) {
      const probabilities = latest.probabilities;
      const probabilitiesLine = document.createElement("p");
      probabilitiesLine.className = "map-popup-probabilities";
      probabilitiesLine.textContent = "Probabilidades estimadas: " + ["Fatal", "Grave", "Leve"]
        .map(name => `${name} ${(probabilities[name] * 100).toFixed(1).replace(".", ",")} %`).join(" · ");
      box.append(probabilitiesLine);
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
    document.getElementById("accident-map").setAttribute("aria-busy", "true");
    error.hidden = true;
    empty.hidden = true;
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
          html: `<span aria-hidden="true">${symbols[severity] || "—"}</span>`,
          iconSize: [44, 44], iconAnchor: [22, 22],
        });
        const name = `${accident.title || `Accidente ${accident.id}`} · ${severity || "Sin análisis ML"}`;
        return L.marker([accident.latitude, accident.longitude], {icon, title: name})
          .on("add", function () { this.getElement().setAttribute("aria-label", name); })
          .bindPopup(popup(accident), {maxWidth: 320, minWidth: 240});
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
      if (!markers.length) {
        empty.textContent = params.size
          ? "No hay accidentes con coordenadas que coincidan con estos filtros."
          : "No hay accidentes con coordenadas registradas para mostrar.";
        empty.hidden = false;
      }
    } catch (failure) {
      if (failure.name === "AbortError" || pending !== request) return;
      clusters.clearLayers();
      status.textContent = "No se pudieron cargar los accidentes.";
      error.hidden = false;
      error.textContent = failure.message;
    } finally {
      if (pending === request) document.getElementById("accident-map").setAttribute("aria-busy", "false");
    }
  }
  filters.addEventListener("submit", event => { event.preventDefault(); load(); });
  filters.addEventListener("change", load);
  filters.addEventListener("reset", () => setTimeout(load, 0));
  new ResizeObserver(() => map.invalidateSize()).observe(document.getElementById("accident-map"));
  load();
})();
