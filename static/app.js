/* SC2 Replay Tracker frontend */
"use strict";

const $ = (sel) => document.querySelector(sel);
const api = (path) => fetch(path).then((r) => r.json());

/* ---------- helpers ---------- */

function fmtDuration(sec) {
  if (sec == null) return "–";
  const m = Math.floor(sec / 60), s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function fmtDate(iso) {
  if (!iso) return "–";
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { year: "2-digit", month: "short", day: "numeric" }) +
         " " + d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function resultPill(result) {
  const cls = result === "Win" ? "result-Win" : result === "Loss" ? "result-Loss" : "result-unknown";
  return `<span class="result-pill ${cls}">${result || "?"}</span>`;
}

function raceSpan(race) {
  if (!race) return "?";
  return `<span class="race-${race[0]}">${race}</span>`;
}

function matchupSpan(mu) {
  if (!mu) return "–";
  return mu.split("").map((c) =>
    "TZP".includes(c) ? `<span class="race-${c}">${c}</span>` : c).join("");
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"]/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

let myNames = [];

function oppLink(name) {
  if (!name) return "?";
  return `<span class="opp-link" data-opp="${esc(name)}">${esc(name)}</span>`;
}

function bindOppLinks(root) {
  root.querySelectorAll(".opp-link").forEach((el) =>
    el.addEventListener("click", (e) => {
      e.stopPropagation();
      openH2H(el.dataset.opp);
    }));
}

/* ---------- tabs ---------- */

document.querySelectorAll(".tab").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.add("hidden"));
    $(`#tab-${btn.dataset.tab}`).classList.remove("hidden");
    if (btn.dataset.tab === "dashboard") loadDashboard();
    if (btn.dataset.tab === "replays") loadReplays();
    if (btn.dataset.tab === "trends") loadTrends();
    if (btn.dataset.tab === "settings") loadSettings();
  });
});

/* ---------- scan indicator ---------- */

let scanWasRunning = false;
async function pollScan() {
  try {
    const s = await api("/api/scan/status");
    const el = $("#scan-indicator");
    if (s.running) {
      el.classList.remove("hidden");
      $("#scan-text").textContent =
        s.total > 0 ? `Importing replays… ${s.done}/${s.total}` : "Scanning…";
      scanWasRunning = true;
    } else {
      el.classList.add("hidden");
      if (scanWasRunning) {
        scanWasRunning = false;
        loadDashboard();   // refresh once a scan completes
      }
    }
  } catch (e) { /* server restarting */ }
  setTimeout(pollScan, scanWasRunning ? 800 : 4000);
}

/* ---------- dashboard ---------- */

function bars(container, rows, labelFn) {
  container.innerHTML = rows.map((r) => `
    <div class="bar-row">
      <div class="bar-label">${labelFn(r.key)}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${r.winrate}%"></div></div>
      <div class="bar-meta">${r.winrate}% &middot; ${r.wins}-${r.losses}</div>
    </div>`).join("") || `<div class="muted">No data</div>`;
}

function fmtMetric(value, fmt) {
  if (value == null) return "–";
  if (fmt === "time") return fmtDuration(Math.round(value));
  if (fmt === "ratio") return Number(value).toFixed(2);
  return Math.round(value * 10) / 10;
}

function renderLatest(data) {
  const el = $("#latest-content");
  if (!data.game) {
    el.innerHTML = `<div class="muted">No games yet</div>`;
    return;
  }
  const g = data.game;
  const tiles = data.metrics.map((m) => {
    let deltaHtml = `<span class="delta neutral">no average yet</span>`;
    if (m.delta_pct != null) {
      const up = m.delta_pct >= 0;
      const arrow = up ? "&#9650;" : "&#9660;";
      let cls = "neutral";
      if (m.good === "up") cls = up ? "good" : "bad";
      if (m.good === "down") cls = up ? "bad" : "good";
      deltaHtml = `<span class="delta ${cls}">${arrow} ${Math.abs(m.delta_pct)}% vs avg</span>`;
    }
    return `
      <div class="metric-tile">
        <div class="m-label">${m.label}</div>
        <div class="m-value">${fmtMetric(m.value, m.fmt)}</div>
        <div class="m-avg muted">avg ${fmtMetric(m.avg, m.fmt)}</div>
        ${deltaHtml}
      </div>`;
  }).join("");

  el.innerHTML = `
    <div class="latest-head" data-id="${g.replay_id}">
      ${resultPill(g.my_result)}
      <span class="latest-mu">${matchupSpan(g.matchup)}</span>
      <span>vs <b>${oppLink(g.opp_name)}</b> (${raceSpan(g.opp_race)}${
        g.opp_mmr ? `, ${Math.round(g.opp_mmr)} MMR` : ""})</span>
      <span class="muted">${esc(g.map_name)} &middot; ${fmtDate(g.played_at)}</span>
      <span class="muted link">details &rarr;</span>
    </div>
    <div class="metric-grid">${tiles}</div>`;
  el.querySelector(".latest-head").addEventListener("click", (e) =>
    openDetail(e.currentTarget.dataset.id));
  bindOppLinks(el);
}

function renderMmrTable(data) {
  const wrap = $("#mmr-table-wrap");
  if (!data.rows.length) {
    wrap.innerHTML = `<div class="muted">No MMR data yet (only ladder games with
      MMR info are counted — data appears after the re-import finishes).</div>`;
    return;
  }
  const wrClass = (wr) => wr >= 55 ? "wr-good" : wr < 45 ? "wr-bad" : "wr-even";
  const head = `<tr><th>Opponent MMR</th>${data.matchups.map((m) =>
    `<th>${matchupSpan(m)}</th>`).join("")}<th>Total</th></tr>`;
  const body = data.rows.map((r) => {
    const cells = data.matchups.map((mu) => {
      const c = r.cells[mu];
      if (!c) return `<td class="muted">–</td>`;
      return `<td><span class="${wrClass(c.winrate)}">${c.winrate}%</span>
              <span class="muted">(${c.wins}-${c.games - c.wins})</span></td>`;
    }).join("");
    return `<tr><td><b>${r.range}</b></td>${cells}
      <td><span class="${wrClass(r.total.winrate)}">${r.total.winrate}%</span>
      <span class="muted">(${r.total.games})</span></td></tr>`;
  }).join("");
  wrap.innerHTML = `<table class="data" id="mmr-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function renderMapTable(data) {
  const wrap = $("#map-table-wrap");
  if (!data.rows.length) {
    wrap.innerHTML = `<div class="muted">No data yet</div>`;
    return;
  }
  const wrClass = (wr) => wr >= 55 ? "wr-good" : wr < 45 ? "wr-bad" : "wr-even";
  const head = `<tr><th>Map</th>${data.matchups.map((m) =>
    `<th>${matchupSpan(m)}</th>`).join("")}<th>Total</th></tr>`;
  const body = data.rows.map((r) => {
    const cells = data.matchups.map((mu) => {
      const c = r.cells[mu];
      if (!c) return `<td class="muted">–</td>`;
      return `<td><span class="${wrClass(c.winrate)}">${c.winrate}%</span>
              <span class="muted">(${c.wins}-${c.games - c.wins})</span></td>`;
    }).join("");
    return `<tr><td>${esc(r.map)}</td>${cells}
      <td><span class="${wrClass(r.total.winrate)}">${r.total.winrate}%</span>
      <span class="muted">(${r.total.games})</span></td></tr>`;
  }).join("");
  wrap.innerHTML = `<table class="data mu-table"><thead>${head}</thead><tbody>${body}</tbody></table>`;
}

function streakCards(streaks) {
  if (!streaks) return "";
  const cur = streaks.current;
  let curHtml = `<div class="value">–</div>`;
  if (cur) {
    const isWin = cur.type === "Win";
    curHtml = `<div class="value" style="color:${isWin ? "var(--win)" : "var(--loss)"}">
      ${cur.length} ${isWin ? "W" : "L"}</div>
      <div class="sub">${isWin ? "wins" : "losses"} in a row</div>`;
  }
  return `
    <div class="card"><div class="label">Current streak</div>${curHtml}</div>
    <div class="card"><div class="label">Longest win streak</div>
      <div class="value" style="color:var(--win)">${streaks.longest_win}</div></div>
    <div class="card"><div class="label">Longest loss streak</div>
      <div class="value" style="color:var(--loss)">${streaks.longest_loss}</div></div>`;
}

async function loadDashboard() {
  const [s, latest, mmr, maps] = await Promise.all([
    api("/api/summary"), api("/api/latest"), api("/api/mmr"), api("/api/mapstats")]);
  myNames = s.player_names || [];
  const empty = s.total_games === 0;
  $("#dash-empty").classList.toggle("hidden", !empty);
  $("#dash-content").classList.toggle("hidden", empty);
  if (empty) return;
  renderLatest(latest);
  renderMmrTable(mmr);
  renderMapTable(maps);

  $("#summary-cards").innerHTML = `
    <div class="card"><div class="label">Player</div>
      <div class="value" style="font-size:18px">${esc(s.player_names.join(", ") || "?")}</div>
      <div class="sub">${s.counts.total} replays in database</div></div>
    <div class="card"><div class="label">1v1 games</div>
      <div class="value">${s.total_games}</div>
      <div class="sub">${s.wins} W &middot; ${s.losses} L</div></div>
    <div class="card"><div class="label">Win rate</div>
      <div class="value" style="color:${s.winrate >= 50 ? "var(--win)" : "var(--loss)"}">${s.winrate}%</div></div>
    <div class="card"><div class="label">Avg APM</div>
      <div class="value">${s.avg_apm ?? "–"}</div></div>
    <div class="card"><div class="label">Avg game length</div>
      <div class="value">${fmtDuration(s.avg_duration)}</div></div>
    ${streakCards(s.streaks)}`;

  bars($("#matchup-bars"), s.by_matchup, matchupSpan);
  bars($("#race-bars"), s.by_my_race, raceSpan);

  $("#recent-table tbody").innerHTML = s.recent.map((g) => `
    <tr data-id="${g.replay_id}">
      <td>${resultPill(g.my_result)}</td>
      <td>${matchupSpan(g.matchup)}</td>
      <td>${oppLink(g.opp_name)}</td>
      <td>${esc(g.map_name)}</td>
      <td class="muted">${fmtDate(g.played_at)}</td>
    </tr>`).join("");
  $("#recent-table tbody").querySelectorAll("tr").forEach((tr) =>
    tr.addEventListener("click", () => openDetail(tr.dataset.id)));
  bindOppLinks($("#recent-table"));
}

/* ---------- replays tab ---------- */

const PAGE_SIZE = 50;
let page = 0;
let filtersLoaded = false;

async function loadFilters() {
  if (filtersLoaded) return;
  filtersLoaded = true;
  const f = await api("/api/filters");
  $("#f-matchup").innerHTML += f.matchups.map((m) => `<option>${esc(m)}</option>`).join("");
  $("#f-map").innerHTML += f.maps.map((m) => `<option>${esc(m)}</option>`).join("");
}

async function loadReplays() {
  await loadFilters();
  const params = new URLSearchParams({
    limit: PAGE_SIZE,
    offset: page * PAGE_SIZE,
  });
  if ($("#f-matchup").value) params.set("matchup", $("#f-matchup").value);
  if ($("#f-map").value) params.set("map_name", $("#f-map").value);
  if ($("#f-result").value) params.set("result", $("#f-result").value);
  if ($("#f-search").value.trim()) params.set("search", $("#f-search").value.trim());

  const data = await api(`/api/replays?${params}`);
  $("#replay-count").textContent = `${data.total} replays`;
  $("#replays-table tbody").innerHTML = data.replays.map((r) => `
    <tr data-id="${r.id}">
      <td>${resultPill(r.my_result)}</td>
      <td>${matchupSpan(r.matchup)}</td>
      <td>${oppLink(r.opp_name)}</td>
      <td>${esc(r.map_name)}</td>
      <td>${fmtDuration(r.duration_seconds)}</td>
      <td>${r.my_apm ?? "–"}</td>
      <td class="muted">${fmtDate(r.played_at)}</td>
    </tr>`).join("");
  $("#replays-table tbody").querySelectorAll("tr").forEach((tr) =>
    tr.addEventListener("click", () => openDetail(tr.dataset.id)));
  bindOppLinks($("#replays-table"));

  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  $("#page-info").textContent = `Page ${page + 1} / ${pages}`;
  $("#prev-page").disabled = page === 0;
  $("#next-page").disabled = page >= pages - 1;
}

["f-matchup", "f-map", "f-result"].forEach((id) =>
  $(`#${id}`).addEventListener("change", () => { page = 0; loadReplays(); }));
let searchTimer;
$("#f-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => { page = 0; loadReplays(); }, 300);
});
$("#prev-page").addEventListener("click", () => { page--; loadReplays(); });
$("#next-page").addEventListener("click", () => { page++; loadReplays(); });

/* ---------- replay detail modal ---------- */

const GRAPH_DEFS = [
  { key: "army", label: "Army Value" },
  { key: "income", label: "Collection Rate" },
  { key: "tech", label: "Upgrade Spending" },
  { key: "workers", label: "Workers Active" },
];
const PLAYER_COLORS = ["#4cc2ff", "#ff5d6c", "#3ddc84", "#ffd24c"];
let detailReplay = null;

function multiLineChart(el, seriesList, { yMax = null, yMin = 0, hline = null, bands = [] } = {}) {
  el.innerHTML = "";
  const usable = seriesList.filter((s) => s.points.length >= 2);
  if (!usable.length) {
    el.innerHTML = `<div class="muted">Not enough data yet
      (a re-import may be required for older imports)</div>`;
    return;
  }
  const W = 900, H = 280, padL = 52, padR = 14, padT = 14, padB = 30;
  const all = usable.flatMap((s) => s.points);
  const xMin = 0, xMax = Math.max(...all.map((p) => p.x));
  const yMaxV = yMax ?? Math.max(...all.map((p) => p.y), 1) * 1.08;
  const sx = (x) => padL + ((x - xMin) / (xMax - xMin || 1)) * (W - padL - padR);
  const sy = (y) => H - padB - ((y - yMin) / (yMaxV - yMin || 1)) * (H - padT - padB);

  let grid = "", labels = "";
  for (let i = 0; i <= 4; i++) {
    const yv = yMin + (i / 4) * (yMaxV - yMin);
    grid += `<line class="axis" x1="${padL}" y1="${sy(yv)}" x2="${W - padR}" y2="${sy(yv)}"/>`;
    labels += `<text x="${padL - 8}" y="${sy(yv) + 4}" text-anchor="end">${Math.round(yv).toLocaleString()}</text>`;
  }
  for (let i = 0; i <= 6; i++) {
    const xv = xMin + (i / 6) * (xMax - xMin);
    labels += `<text x="${sx(xv)}" y="${H - 8}" text-anchor="middle">${fmtDuration(Math.round(xv))}</text>`;
  }
  let bandsSvg = "";
  for (const b of bands) {
    const x1 = sx(Math.max(b.x1, xMin));
    const x2 = sx(Math.min(b.x2, xMax));
    bandsSvg += `<rect x="${x1.toFixed(1)}" y="${padT}"
      width="${Math.max(x2 - x1, 3).toFixed(1)}" height="${H - padT - padB}"
      fill="#ff5d6c" opacity="0.13"/>`;
  }
  let hlineSvg = "";
  if (hline != null && hline >= yMin && hline <= yMaxV) {
    hlineSvg = `<line x1="${padL}" y1="${sy(hline)}" x2="${W - padR}" y2="${sy(hline)}"
      stroke="var(--loss)" stroke-width="1" opacity="0.55"/>`;
  }
  const paths = usable.map((s) => {
    const d = s.points.map((p, i) =>
      `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
    return `<path class="mline" style="stroke:${s.color}" d="${d}"/>`;
  }).join("");
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${grid}${labels}${bandsSvg}${hlineSvg}${paths}</svg>`;
}

const MU_COLORS = { T: "#6ea8ff", Z: "#b97aff", P: "#ffd24c" };
const muColor = (mu) => MU_COLORS[mu[2]] || "#4cc2ff";

function muLegend(el, series) {
  el.innerHTML = series.map((s) => `
    <span class="legend-item"><span class="legend-dot"
      style="background:${s.color}"></span>${matchupSpan(s.key)}</span>`).join("");
}

function renderDetailGraph(graphKey) {
  document.querySelectorAll(".chart-tabs button").forEach((b) =>
    b.classList.toggle("active", b.dataset.graph === graphKey));
  const series = detailReplay.players.map((p, i) => ({
    name: p.name,
    color: PLAYER_COLORS[i % PLAYER_COLORS.length],
    points: (p.timeseries || [])
      .filter((s) => s[graphKey] != null)
      .map((s) => ({ x: s.t, y: s[graphKey] })),
  }));
  const bands = (detailReplay.fights || []).map((f) =>
    ({ x1: f.start, x2: Math.max(f.end, f.start + 5) }));
  multiLineChart($("#detail-chart"), series, { bands });
}

function fightsSection(r) {
  const fights = r.fights || [];
  if (!fights.length) return "";
  const rows = fights.map((f) => {
    const sides = r.players.map((p, i) => {
      const L = f.losses[String(p.pid)] || { value: 0, units: {} };
      const units = Object.entries(L.units)
        .sort((a, b) => b[1] - a[1]).slice(0, 6)
        .map(([n, c]) => `${c}&times; ${esc(n)}`).join(", ");
      return `<div class="fight-side">
        <span class="legend-dot" style="background:${PLAYER_COLORS[i % PLAYER_COLORS.length]}"></span>
        <b>&minus;${L.value.toLocaleString()}</b>
        <span class="muted">${units || "no losses"}</span></div>`;
    }).join("");
    const winner = r.players.find((p) => p.pid === f.winner_pid);
    const outcome = winner
      ? `<span class="${winner.result === "Win" ||
          (myNames.length && myNames.includes(winner.name))
          ? "wr-good" : ""}" style="color:${
          PLAYER_COLORS[r.players.indexOf(winner) % PLAYER_COLORS.length]}">
          ${esc(winner.name)} won trade</span>`
      : `<span class="muted">even trade</span>`;
    return `<div class="fight-row">
      <div class="fight-time">${fmtDuration(f.start)}</div>
      <div class="fight-sides">${sides}</div>
      <div class="fight-outcome">${outcome}</div>
    </div>`;
  }).join("");
  return `<div class="fights-section">
    <h4>Fights <span class="muted">(${fights.length} engagements,
      shaded on the graphs above)</span></h4>${rows}</div>`;
}

async function openDetail(id) {
  const r = await api(`/api/replay/${id}`);
  detailReplay = r;
  const playersHtml = r.players.map((p, i) => `
    <div class="player-box" style="border-top: 3px solid ${PLAYER_COLORS[i % PLAYER_COLORS.length]}">
      <h3>${myNames.includes(p.name) ? esc(p.name) : oppLink(p.name)}
          ${resultPill(p.result)}</h3>
      <div class="stats">
        ${raceSpan(p.race)}
        ${p.mmr ? ` &middot; ${Math.round(p.mmr)} MMR` : ""}
        &middot; APM ${p.apm ?? "–"}
        ${p.spm ? ` &middot; SPM ${p.spm}` : ""}
        ${p.is_human ? "" : " &middot; AI"}
      </div>
      <div class="bo-list">
        ${p.build_order.map((b) =>
          `<div><span class="t">${fmtDuration(b.second)}</span><span>${esc(b.name)}</span></div>`
        ).join("") || `<div class="muted">No build order data</div>`}
      </div>
    </div>`).join("");

  $("#modal-content").innerHTML = `
    <div class="detail-head">
      <h2>${esc(r.map_name)} &mdash; ${matchupSpan(r.matchup)}</h2>
      <div class="detail-meta">
        ${fmtDate(r.played_at)} &middot; ${fmtDuration(r.duration_seconds)}
        &middot; ${esc(r.game_type || "")} ${esc(r.category || "")}
        &middot; v${esc(r.version || "?")}
        <br><span style="font-size:11px">${esc(r.filename)}</span>
        <button class="mini" id="reveal-btn">Open file location</button>
      </div>
    </div>
    <div class="detail-graphs">
      <div class="chart-tabs">
        ${GRAPH_DEFS.map((g) =>
          `<button data-graph="${g.key}">${g.label}</button>`).join("")}
        <span class="legend">
          ${r.players.map((p, i) =>
            `<span class="legend-item"><span class="legend-dot"
              style="background:${PLAYER_COLORS[i % PLAYER_COLORS.length]}"></span>${esc(p.name)}</span>`).join("")}
        </span>
      </div>
      <div id="detail-chart" class="chart"></div>
    </div>
    ${fightsSection(r)}
    <div class="players-grid">${playersHtml}</div>`;
  document.querySelectorAll(".chart-tabs button").forEach((b) =>
    b.addEventListener("click", () => renderDetailGraph(b.dataset.graph)));
  renderDetailGraph("army");
  bindOppLinks($("#modal-content"));
  $("#reveal-btn").addEventListener("click", async (e) => {
    e.stopPropagation();
    const res = await fetch(`/api/reveal/${r.id}`, { method: "POST" });
    if (!res.ok) {
      e.target.textContent = "File not found on disk";
      e.target.disabled = true;
    }
  });
  $("#modal").classList.remove("hidden");
}

/* ---------- head-to-head (opponent match history) ---------- */

async function openH2H(name) {
  const h = await api(`/api/vs?name=${encodeURIComponent(name)}`);
  const muHtml = h.by_matchup.map((m) => `
    <span class="h2h-mu">${matchupSpan(m.key)}
      <span class="${m.winrate >= 50 ? "wr-good" : "wr-bad"}">${m.winrate}%</span>
      <span class="muted">(${m.wins}-${m.losses})</span></span>`).join("");

  const gamesHtml = h.games.map((g) => `
    <tr data-id="${g.replay_id}">
      <td>${resultPill(g.my_result)}</td>
      <td>${matchupSpan(g.matchup)}</td>
      <td>${esc(g.map_name)}</td>
      <td>${fmtDuration(g.duration_seconds)}</td>
      <td>${g.opp_mmr ? Math.round(g.opp_mmr) : "–"}</td>
      <td class="muted">${fmtDate(g.played_at)}</td>
    </tr>`).join("");

  $("#modal-content").innerHTML = `
    <div class="detail-head">
      <h2>vs ${esc(h.name)}</h2>
      <div class="detail-meta">
        <span class="${h.winrate >= 50 ? "wr-good" : "wr-bad"}"
          style="font-size:16px">${h.winrate}%</span>
        &middot; ${h.wins}-${h.losses} in ${h.total} game${h.total === 1 ? "" : "s"}
        ${h.avg_opp_mmr ? ` &middot; avg ${h.avg_opp_mmr} MMR` : ""}
      </div>
      <div class="h2h-matchups">${muHtml}</div>
    </div>
    ${h.total ? `
    <table class="data clickable">
      <thead><tr><th>Result</th><th>Matchup</th><th>Map</th><th>Length</th>
        <th>Opp MMR</th><th>Played</th></tr></thead>
      <tbody>${gamesHtml}</tbody>
    </table>` : `<div class="muted">No games found against this player.</div>`}`;

  $("#modal-content").querySelectorAll("tr[data-id]").forEach((tr) =>
    tr.addEventListener("click", () => openDetail(tr.dataset.id)));
  $("#modal").classList.remove("hidden");
}

$("#modal-close").addEventListener("click", () => $("#modal").classList.add("hidden"));
$("#modal").addEventListener("click", (e) => {
  if (e.target === $("#modal")) $("#modal").classList.add("hidden");
});

/* ---------- trends (dependency-free SVG charts) ---------- */

function rollingAvg(points, window) {
  // points: [{x, y, label}] -> rolling mean of y over the trailing `window`
  const out = [];
  let sum = 0;
  for (let i = 0; i < points.length; i++) {
    sum += points[i].y;
    if (i >= window) sum -= points[i - window].y;
    const n = Math.min(i + 1, window);
    out.push({ ...points[i], y: sum / n });
  }
  return out;
}

function lineChart(el, points, { yMax = null, dots = null, raw = null } = {}) {
  el.innerHTML = "";
  if (points.length < 2) {
    el.innerHTML = `<div class="muted">Not enough data yet</div>`;
    return;
  }
  const W = 900, H = 260, padL = 46, padR = 14, padT = 14, padB = 30;
  const all = raw ? points.concat(raw) : points;
  const xs = all.map((p) => p.x), ys = all.map((p) => p.y);
  const xMin = Math.min(...xs), xMax = Math.max(...xs);
  const yMin = 0;
  const yMaxV = yMax ?? Math.max(...ys) * 1.1;
  const sx = (x) => padL + ((x - xMin) / (xMax - xMin || 1)) * (W - padL - padR);
  const sy = (y) => H - padB - ((y - yMin) / (yMaxV - yMin || 1)) * (H - padT - padB);

  let grid = "", labels = "";
  for (let i = 0; i <= 4; i++) {
    const yv = yMin + (i / 4) * (yMaxV - yMin);
    const ypx = sy(yv);
    grid += `<line class="axis" x1="${padL}" y1="${ypx}" x2="${W - padR}" y2="${ypx}"/>`;
    labels += `<text x="${padL - 8}" y="${ypx + 4}" text-anchor="end">${Math.round(yv)}</text>`;
  }
  // x labels: first, middle, last
  [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]].forEach((p) => {
    labels += `<text x="${sx(p.x)}" y="${H - 8}" text-anchor="middle">${p.label || ""}</text>`;
  });

  const path = points.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
  let rawSvg = "";
  if (raw) {
    rawSvg = raw.map((p) =>
      `<circle class="raw" cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="2.5">
         <title>${p.title || ""}</title></circle>`).join("");
  }
  let dotsSvg = "";
  if (dots) {
    dotsSvg = points.map((p) =>
      `<circle class="${dots(p)}" cx="${sx(p.x).toFixed(1)}" cy="${sy(p.y).toFixed(1)}" r="3">
         <title>${p.title || ""}</title></circle>`).join("");
  }
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}">${grid}${labels}${rawSvg}
    <path class="line" d="${path}"/>${dotsSvg}</svg>`;
}

async function loadTrends() {
  const [t, dur] = await Promise.all([api("/api/trends"), api("/api/duration")]);

  const winSeries = dur.matchups.map((mu) => ({
    key: mu.key,
    color: muColor(mu.key),
    points: mu.points.map((p) => ({ x: p.m * 60, y: p.winrate })),
  }));
  muLegend($("#legend-durwin"), winSeries);
  multiLineChart($("#chart-durwin"), winSeries, { yMax: 100, hline: 50 });

  const countSeries = dur.matchups.map((mu) => ({
    key: mu.key,
    color: muColor(mu.key),
    points: mu.points.map((p) => ({ x: p.m * 60, y: p.count })),
  }));
  muLegend($("#legend-durcount"), countSeries);
  multiLineChart($("#chart-durcount"), countSeries);

  const winPts = t.games_series.map((g) => ({
    x: new Date(g.played_at).getTime(), y: g.win * 100,
    label: new Date(g.played_at).toLocaleDateString(),
  }));
  lineChart($("#chart-winrate"), rollingAvg(winPts, 50), { yMax: 100 });

  const apmPts = t.apm_series.map((g) => ({
    x: new Date(g.played_at).getTime(), y: g.apm,
    label: new Date(g.played_at).toLocaleDateString(),
    title: `${g.matchup || ""} ${g.apm} APM`,
  }));
  lineChart($("#chart-apm"), rollingAvg(apmPts, 20), { raw: apmPts });

  const durPts = t.duration_series.map((g) => ({
    x: new Date(g.played_at).getTime(), y: g.minutes,
    label: new Date(g.played_at).toLocaleDateString(),
    title: `${g.minutes} min`,
  }));
  lineChart($("#chart-duration"), rollingAvg(durPts, 20), { raw: durPts });
}

/* ---------- settings ---------- */

async function loadSettings() {
  const s = await api("/api/settings");
  $("#s-names").value = s.player_names.join(", ");
  $("#s-dirs").value = s.replay_dirs.join("\n");
  const missing = Object.entries(s.dirs_exist).filter(([, ok]) => !ok).map(([d]) => d);
  $("#s-dirs-status").textContent = missing.length
    ? `Warning - folder not found: ${missing.join("; ")}` : "";
  const c = await api("/api/summary");
  $("#s-counts").textContent =
    `${c.counts.total} replays imported, ${c.counts.errors} unreadable files skipped.`;
}

$("#s-save").addEventListener("click", async () => {
  const body = {
    player_names: $("#s-names").value.split(",").map((s) => s.trim()).filter(Boolean),
    replay_dirs: $("#s-dirs").value.split("\n").map((s) => s.trim()).filter(Boolean),
  };
  await fetch("/api/settings", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  $("#s-msg").textContent = "Saved.";
  setTimeout(() => ($("#s-msg").textContent = ""), 2500);
  loadSettings();
});

$("#s-rescan").addEventListener("click", async () => {
  await fetch("/api/scan", { method: "POST" });
  scanWasRunning = true;
  $("#s-msg").textContent = "Scan started…";
  setTimeout(() => ($("#s-msg").textContent = ""), 2500);
});

/* ---------- boot ---------- */

loadDashboard();
pollScan();
