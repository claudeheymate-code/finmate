/* Finmate — panel web. Carga los datos desde /api/* y arma cada pantalla.
   Todo texto que viene del usuario o de la base pasa por esc() antes de
   entrar al HTML. */
(function () {
  "use strict";

  const CAT_COLORS = {
    "Comidas": "#FFB37A", "Carretes": "#009B77", "Asados": "#E2725B", "Regalos": "#3DDBB0",
    "Suscripciones": "#5AA9FF", "Polola": "#FF8FB1", "Copete": "#A99BFF", "Bets": "#E9B949", "Otros": "#94A3B8",
  };
  // Las categorías propias de cada usuario reciben un color estable según su nombre
  const EXTRA_COLORS = ["#7FDBDA", "#B8E986", "#FF9F9F", "#9FB4FF", "#E0A3FF", "#FFD39F", "#8FE3B0", "#A7C7E7"];
  function catColor(name) {
    if (CAT_COLORS[name]) return CAT_COLORS[name];
    let h = 0; for (const ch of String(name)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
    return EXTRA_COLORS[h % EXTRA_COLORS.length];
  }
  const PALETTE = ["#009B77", "#2F7FD8", "#3DDBB0", "#8B7CF0", "#F59E5B", "#F27BA0", "#94A3B8", "#082448"];
  const CLASS_COLORS = { "Renta variable": "#009B77", "Renta fija": "#5AA9FF" };
  const MONTHS = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

  // ---------- utilidades ----------
  const $ = (sel) => document.querySelector(sel);
  function esc(v) {
    return String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  function sep(n, dec) {
    const parts = Math.abs(n).toFixed(dec).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ".");
    return parts.join(",");
  }
  const sign = (n) => (n > 0 ? "+" : n < 0 ? "−" : "");
  const usd = (n, signed) => (n == null ? "—" : (signed ? sign(n) : n < 0 ? "−" : "") + "USD " + sep(n, 2));
  const clp = (n, signed) => (n == null ? "—" : (signed ? sign(n) : n < 0 ? "−" : "") + "$" + sep(n, 0));
  const pct = (n, signed) => (n == null ? "—" : Math.abs(n) < 0.005 ? "0%" : (signed === false ? "" : sign(n)) + sep(n, Math.abs(n) < 1 ? 2 : 1) + "%");
  function delta(text, up) {
    return '<span class="delta ' + (up ? "up" : "down") + '">' + (up ? "▲" : "▼") + " " + esc(text) + "</span>";
  }
  function box(cls, msg) { return '<p class="' + cls + '">' + esc(msg) + "</p>"; }

  async function api(method, path, body) {
    const opts = { method: method, credentials: "same-origin", headers: { "X-Finmate": "1" } };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    // Sin respuesta en un tiempo razonable se avisa, en vez de quedar "Cargando…" para siempre.
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), path === "/chat" ? 90000 : 20000);
    opts.signal = ctrl.signal;
    let r;
    try { r = await fetch("/api" + path, opts); }
    catch (e) {
      throw new Error(e.name === "AbortError" ? "Finmate está tardando más de lo normal. Intenta de nuevo en un momento."
                                              : "Sin conexión. Revisa tu internet e intenta de nuevo.");
    } finally { clearTimeout(timer); }
    if (r.status === 401 && document.body.dataset.page !== "acceso") { location.href = "/panel/acceso"; throw new Error("no_autenticado"); }
    let data = null;
    try { data = await r.json(); } catch (e) { data = null; }
    if (!r.ok) throw new Error((data && data.error) || "Algo falló. Intenta de nuevo.");
    return data;
  }

  /* Torta (donut) con conic-gradient + leyenda.
     parts: [{name, value, color}]; opts: {center, centerLabel, money, onPick, selected} */
  function donut(el, parts, opts) {
    opts = opts || {};
    const money = opts.money || usd;
    const total = parts.reduce((a, p) => a + (p.value || 0), 0);
    let acc = 0;
    const stops = [];
    parts.forEach((p) => {
      if (!p.value) return;
      const a = (acc / total) * 100; acc += p.value; const b = (acc / total) * 100;
      stops.push(p.color + " " + a.toFixed(2) + "% " + b.toFixed(2) + "%");
    });
    const bg = stops.length ? "conic-gradient(" + stops.join(", ") + ")" : "#EDF1F5";
    const aria = (opts.centerLabel || "Distribución") + ": " + parts.map((p) => p.name + " " + pct(total ? (p.value / total) * 100 : 0, false)).join(", ");
    const items = parts.map((p) => {
      const inner = '<span class="dot" style="background:' + p.color + '"></span><span class="name">' + esc(p.name) + '</span><span class="faint small">' + esc(money(p.value)) + '</span><span class="pct">' + esc(pct(total ? (p.value / total) * 100 : 0, false)) + "</span>";
      if (opts.onPick) {
        return '<li><button type="button" data-name="' + esc(p.name) + '" aria-pressed="' + (opts.selected === p.name) + '">' + inner + "</button></li>";
      }
      return '<li><div class="item">' + inner + "</div></li>";
    }).join("");
    el.innerHTML =
      '<div class="donut" role="img" aria-label="' + esc(aria) + '" style="background:' + bg + '"><div class="hole"><span class="faint small">' + esc(opts.centerLabel || "Total") + '</span><span class="num">' + esc(opts.center != null ? opts.center : money(total)) + "</span></div></div>" +
      '<ul class="legend">' + (items || '<li class="faint">Sin datos todavía</li>') + "</ul>";
    if (opts.onPick) {
      el.querySelectorAll("button[data-name]").forEach((b) => b.addEventListener("click", () => opts.onPick(b.dataset.name)));
    }
  }

  // ---------- idioma de la app (ver i18n.js) ----------
  function initLang() {
    const i18n = window.FinmateI18n; if (!i18n) return;
    const btns = document.querySelectorAll("[data-lang]");
    const paint = () => btns.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.lang === i18n.get())));
    btns.forEach((b) => b.addEventListener("click", () => { i18n.set(b.dataset.lang); paint(); }));
    paint();
  }

  // ---------- comunes: preguntar al bot y salir ----------
  function initShell() {
    const form = $("#ask-form");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const input = $("#ask-input"); const pop = $("#ask-pop");
        const q = input.value.trim(); if (!q) return;
        pop.hidden = false;
        pop.innerHTML = '<p class="bubble me">' + esc(q) + '</p><p class="bubble bot faint">Pensando…</p>';
        input.value = "";
        try {
          const r = await api("POST", "/chat", { message: q });
          pop.innerHTML = '<p class="bubble me">' + esc(q) + '</p><p class="bubble bot">' + esc(r.reply) + '</p><button class="btn ghost" type="button" id="ask-close" style="align-self:flex-end">Cerrar</button>';
        } catch (err) {
          pop.innerHTML = '<p class="bubble me">' + esc(q) + "</p>" + box("error-box", err.message) + '<button class="btn ghost" type="button" id="ask-close" style="align-self:flex-end">Cerrar</button>';
        }
        const c = $("#ask-close"); if (c) c.addEventListener("click", () => { pop.hidden = true; });
      });
    }
    const out = $("#logout");
    if (out) out.addEventListener("click", async () => { try { await api("POST", "/auth/logout"); } catch (e) {} location.href = "/panel/acceso"; });
  }

  // ---------- Resumen ----------
  async function pageResumen() {
    let d;
    try { d = await api("GET", "/resumen"); } catch (e) { $("#r-stats").innerHTML = box("error-box", e.message); return; }
    const t = d.portfolio.totals; const f = d.finanzas;
    const stat = (label, value, sub) => '<section class="card glass stat"><p class="label">' + esc(label) + '</p><p class="value">' + esc(value) + '</p><div class="sub">' + sub + "</div></section>";
    const diffTxt = f.prev_total_gastos ? (f.diff <= 0 ? clp(-f.diff) + " menos que el mes pasado" : clp(f.diff) + " más que el mes pasado") : f.count + " gastos registrados";
    $("#r-stats").innerHTML =
      stat("Valor del portafolio", t.count ? usd(t.value) : "—", t.count ? delta(usd(t.day_change, true) + " hoy (" + pct(t.day_change_pct) + ")", t.day_change >= 0) : '<span>Todavía no has cargado posiciones</span>') +
      stat("Ganancia total", t.pnl != null ? usd(t.pnl, true) : "—", t.pnl != null ? delta(pct(t.pnl_pct) + " sobre lo invertido", t.pnl >= 0) : "<span>Carga el precio promedio para calcularla</span>") +
      stat("Gastos de " + MONTHS[f.month - 1], clp(f.total_gastos), "<span>" + esc(diffTxt) + (f.top_category ? " · más en " + esc(f.top_category) : "") + "</span>") +
      stat("Alertas activas", String(d.watchlist.length), "<span>" + (d.watchlist.length ? "Watchlist, si algo se mueve más de " + esc(pct(d.avisos.watchlist_threshold_pct, false)) : "Sigue un activo para recibir alertas") + "</span>");

    const rows = [];
    d.portfolio.top_positions.forEach((p) => rows.push(assetRow(p.symbol, "En tu portafolio · " + sep(p.quantity, p.quantity % 1 ? 2 : 0) + " u.", p.price, p.change_pct)));
    d.watchlist.forEach((w) => rows.push(assetRow(w.symbol, "En tu watchlist", w.price, w.change_pct)));
    $("#r-assets").innerHTML = rows.join("") || '<li class="empty">Agrega posiciones o sigue activos desde Mis inversiones.</li>';

    $("#r-chat").innerHTML = d.chat.length
      ? d.chat.map((m) => '<p class="bubble ' + (m.role === "user" ? "me" : "bot") + '">' + esc(m.content.length > 280 ? m.content.slice(0, 280) + "…" : m.content) + "</p>").join("")
      : '<p class="faint">Todavía no hay conversación. Escríbele a Finmate por WhatsApp o desde la barra de arriba.</p>';

    const s = d.seguimientos; const fl = [];
    s.indicadores.forEach((i) => fl.push('<li><div class="grow"><p class="strong">' + esc(i.name) + '</p><p class="faint small">' + esc(i.freq) + " · relevancia " + esc(i.relevance) + '</p></div><span class="muted small">Indicador</span></li>'));
    s.temas.forEach((t2) => fl.push('<li><div class="grow"><p class="strong">' + esc(t2.valor) + '</p><p class="faint small">Tema de noticias · ' + esc(t2.tipo) + '</p></div><span class="muted small">Siguiendo</span></li>'));
    $("#r-follows").innerHTML = fl.join("") || '<li class="empty">No sigues nada todavía. Agrégalo en Ajustes.</li>';
  }
  function assetRow(sym, sub, price, chg) {
    return '<li><span class="ticker">' + esc(sym.slice(0, 5)) + '</span><div class="grow"><p class="strong">' + esc(sym) + '</p><p class="faint small">' + esc(sub) + '</p></div><div class="right"><p class="strong">' + esc(usd(price)) + "</p>" + (chg != null ? delta(pct(chg), chg >= 0) : "") + "</div></li>";
  }

  // ---------- Inversiones ----------
  async function pageInversiones() {
    async function load() {
      let d;
      try { d = await api("GET", "/portafolio"); } catch (e) { $("#i-error").innerHTML = box("error-box", e.message); return; }
      $("#i-error").innerHTML = d.missing_prices.length ? box("error-box", "Sin precio ahora para: " + d.missing_prices.join(", ") + ". No cuentan en los totales.") : "";
      const t = d.totals;
      const mover = (p, i) => '<li><span class="faint num" style="width:18px">' + (i + 1) + '</span><span class="ticker">' + esc(p.symbol.slice(0, 5)) + '</span><div class="grow"><p class="strong">' + esc(p.symbol) + '</p><p class="faint small">' + esc(usd(p.pnl, true)) + "</p></div>" + delta(pct(p.pnl_pct), p.pnl_pct >= 0) + "</li>";
      $("#i-winners").innerHTML = d.top_winners.map(mover).join("") || '<li class="empty">Ninguna posición en ganancia todavía.</li>';
      $("#i-losers").innerHTML = d.top_losers.map(mover).join("") || '<li class="empty">Ninguna posición en pérdida. Bien ahí.</li>';
      donut($("#i-class"), d.by_class.map((g) => ({ name: g.name, value: g.value, color: CLASS_COLORS[g.name] || "#94A3B8" })), { centerLabel: "Tipo de activo", center: d.by_class.length + (d.by_class.length === 1 ? " grupo" : " grupos") });
      donut($("#i-sector"), d.by_sector.map((g, i) => ({ name: g.name, value: g.value, color: PALETTE[i % PALETTE.length] })), { centerLabel: "Sectores", center: d.by_sector.length + (d.by_sector.length === 1 ? " sector" : " sectores") });
      $("#i-totals").innerHTML =
        '<div><p class="faint small">Valor total</p><p class="num strong" style="font-size:22px">' + esc(usd(t.value)) + "</p></div>" +
        '<div><p class="faint small">Invertido</p><p class="num strong" style="font-size:22px">' + esc(usd(t.cost)) + "</p></div>" +
        '<div><p class="faint small">Ganancia</p><p style="font-size:18px">' + (t.pnl != null ? delta(usd(t.pnl, true) + " (" + pct(t.pnl_pct) + ")", t.pnl >= 0) : "—") + "</p></div>";
      $("#i-rows").innerHTML = d.positions.map((p) =>
        "<tr><td><strong>" + esc(p.symbol) + '</strong><br><span class="faint small">' + esc(p.asset_class) + " · " + esc(p.sector) + "</span></td>" +
        '<td class="r">' + esc(sep(p.quantity, p.quantity % 1 ? 2 : 0)) + '</td><td class="r">' + esc(usd(p.avg_cost)) + '</td><td class="r">' + esc(usd(p.price)) + "</td>" +
        '<td class="r">' + (p.change_pct != null ? delta(pct(p.change_pct), p.change_pct >= 0) : "—") + '</td><td class="r strong">' + esc(usd(p.value)) + "</td>" +
        '<td class="r">' + (p.pnl != null ? delta(usd(p.pnl, true) + " · " + pct(p.pnl_pct), p.pnl >= 0) : "—") + '</td><td class="r">' + esc(p.weight_pct != null ? pct(p.weight_pct, false) : "—") + "</td>" +
        '<td class="r"><button class="icon-btn" type="button" data-del="' + esc(p.symbol) + '" aria-label="Quitar ' + esc(p.symbol) + ' del portafolio">✕</button></td></tr>'
      ).join("") || '<tr><td colspan="9" class="empty">Todavía no has cargado posiciones. Usa el formulario de abajo o escríbele al bot.</td></tr>';
      document.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => {
        if (!window.confirm("¿Quitar " + b.dataset.del + " de tu portafolio?")) return;
        try { await api("DELETE", "/portafolio/" + encodeURIComponent(b.dataset.del)); load(); } catch (e) { $("#i-error").innerHTML = box("error-box", e.message); }
      }));
      $("#i-updated").textContent = "Actualizado " + new Date().toLocaleTimeString(document.documentElement.lang === "en" ? "en-US" : "es-CL", { hour: "2-digit", minute: "2-digit" });
    }
    async function loadWatch() {
      try {
        const w = await api("GET", "/watchlist");
        $("#i-watch").innerHTML = w.items.map((it) =>
          '<li><span class="ticker">' + esc(it.symbol.slice(0, 5)) + '</span><div class="grow"><p class="strong">' + esc(it.symbol) + '</p><p class="faint small">Aviso si se mueve más de ' + esc(pct(it.threshold_pct, false)) + ' en el día</p></div><div class="right"><p class="strong">' + esc(usd(it.price)) + "</p>" + (it.change_pct != null ? delta(pct(it.change_pct), it.change_pct >= 0) : "") +
          '</div><button class="btn ghost" type="button" data-why="' + esc(it.symbol) + '">¿Por qué se movió?</button><button class="icon-btn" type="button" data-unwatch="' + esc(it.symbol) + '" aria-label="Dejar de seguir ' + esc(it.symbol) + '">✕</button></li>'
        ).join("") || '<li class="empty">No sigues ningún activo todavía.</li>';
        document.querySelectorAll("[data-unwatch]").forEach((b) => b.addEventListener("click", async () => { await api("DELETE", "/watchlist/" + encodeURIComponent(b.dataset.unwatch)); loadWatch(); }));
        document.querySelectorAll("[data-why]").forEach((b) => b.addEventListener("click", async () => {
          const el = $("#explain"); el.innerHTML = '<p class="faint">Buscando noticias…</p>';
          try {
            const x = await api("GET", "/mercado/explicar/" + encodeURIComponent(b.dataset.why));
            el.innerHTML = '<div class="ok-box" style="color:var(--text)"><p class="strong">' + esc(x.symbol) + " · " + esc(usd(x.price)) + " " + (x.change_pct != null ? delta(pct(x.change_pct), x.change_pct >= 0) : "") + "</p>" +
              (x.news.length ? '<ul style="margin:8px 0 0;padding-left:18px">' + x.news.map((n) => "<li>" + (n.url ? '<a href="' + esc(n.url) + '" target="_blank" rel="noopener">' + esc(n.headline) + "</a>" : esc(n.headline)) + ' <span class="faint small">' + esc(n.source) + "</span></li>").join("") + "</ul>" : '<p class="faint small">No encontré noticias recientes que hablen de este activo.</p>') + "</div>";
          } catch (e) { el.innerHTML = box("error-box", e.message); }
        }));
      } catch (e) { $("#i-watch").innerHTML = '<li class="empty">' + esc(e.message) + "</li>"; }
    }
    $("#add-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("POST", "/portafolio", { symbol: $("#f-sym").value, quantity: $("#f-qty").value, avg_cost: $("#f-avg").value || null });
        $("#add-msg").innerHTML = box("ok-box", "Listo, posición guardada."); e.target.reset(); load();
      } catch (err) { $("#add-msg").innerHTML = box("error-box", err.message); }
    });
    $("#watch-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("POST", "/watchlist", { symbol: $("#f-wsym").value }); e.target.reset(); loadWatch(); } catch (err) { $("#explain").innerHTML = box("error-box", err.message); }
    });
    load(); loadWatch();
  }

  // ---------- Gastos ----------
  async function pageGastos() {
    const now = new Date();
    const state = { year: now.getFullYear(), month: now.getMonth() + 1, cat: null, sel: null, items: [], newCat: null, cats: [] };
    const prevYM = () => (state.month === 1 ? [state.year - 1, 12] : [state.year, state.month - 1]);

    async function loadSummary() {
      const r = await api("GET", "/finanzas/resumen?anio=" + state.year + "&mes=" + state.month);
      const a = r.actual, p = r.anterior, y = r.anio;
      const diff = a.total_gastos - p.total_gastos;
      $("#g-cur-title").textContent = cap(MONTHS[a.month - 1]) + " " + a.year;
      $("#g-ytd-title").textContent = "En lo que va de " + y.year;
      $("#g-th-cur").textContent = cap(MONTHS[a.month - 1]).slice(0, 3);
      $("#g-th-prev").textContent = "Lst Mth";
      $("#g-th-prev").title = cap(MONTHS[p.month - 1]) + " " + p.year;
      $("#g-stats").innerHTML =
        '<section class="card glass stat"><p class="label">Gastado en ' + esc(MONTHS[a.month - 1]) + '</p><p class="value">' + esc(clp(a.total_gastos)) + '</p><p class="sub">' + a.count + " gastos registrados</p></section>" +
        '<section class="card glass stat"><p class="label">Gastado en ' + esc(MONTHS[p.month - 1]) + '</p><p class="value">' + esc(clp(p.total_gastos)) + '</p><p class="sub">Mes anterior</p></section>' +
        '<section class="card glass stat"><p class="label">Diferencia</p><p class="value ' + (diff > 0 ? "down" : "up") + '">' + esc(clp(diff, true)) + '</p><p class="sub">' + (diff > 0 ? "Vas gastando más que el mes pasado" : "Vas gastando menos que el mes pasado") + "</p></section>";
      const toParts = (m) => m.categories.map((c) => ({ name: c.name, value: c.amount, color: catColor(c.name) }));
      donut($("#g-cur"), toParts(a), { money: clp, centerLabel: "Total", selected: state.cat, onPick: pickCat });
      donut($("#g-ytd"), toParts(y), { money: clp, centerLabel: "Total " + y.year });
      // Tabla comparativa: todas las categorías que aparecen en alguno de los dos meses
      const prevBy = {}; p.categories.forEach((c) => { prevBy[c.name] = c.amount; });
      const names = a.categories.map((c) => c.name);
      p.categories.forEach((c) => { if (names.indexOf(c.name) < 0 && c.amount) names.splice(Math.max(names.length - 1, 0), 0, c.name); });
      const curBy = {}; a.categories.forEach((c) => { curBy[c.name] = c.amount; });
      const cell = (d) => (d === 0 ? '<span class="faint">—</span>' : '<span class="' + (d > 0 ? "down" : "up") + '">' + esc(clp(d, true)) + "</span>");
      $("#g-cmp").innerHTML = names.map((n) => {
        const c = curBy[n] || 0, pv = prevBy[n] || 0;
        return '<tr' + (state.cat === n ? ' class="sel"' : "") + '><td><button type="button" class="cmp-cat" data-cmp="' + esc(n) + '"><span class="dot" style="width:10px;height:10px;background:' + catColor(n) + '"></span><span class="cat-name">' + esc(n) + '</span></button></td><td class="r">' + (c ? esc(clp(c)) : '<span class="faint">$0</span>') + '</td><td class="r">' + (pv ? esc(clp(pv)) : '<span class="faint">$0</span>') + '</td><td class="r">' + cell(c - pv) + "</td></tr>";
      }).join("");
      $("#g-cmp-total").innerHTML = '<tr><td class="strong">Total</td><td class="r strong">' + esc(clp(a.total_gastos)) + '</td><td class="r strong">' + esc(clp(p.total_gastos)) + '</td><td class="r strong">' + cell(diff) + "</td></tr>";
      document.querySelectorAll("[data-cmp]").forEach((b) => b.addEventListener("click", () => pickCat(b.dataset.cmp)));
    }
    async function loadList() {
      const q = "/finanzas/movimientos?anio=" + state.year + "&mes=" + state.month + (state.cat ? "&categoria=" + encodeURIComponent(state.cat) : "");
      const r = await api("GET", q);
      state.items = r.items.filter((t) => t.amount < 0);
      $("#g-list-title").textContent = state.cat ? "Gastos en " + state.cat : "Todos los gastos";
      $("#g-list").innerHTML = state.items.map((t) =>
        '<li><button type="button" data-tx="' + t.id + '" aria-pressed="' + (state.sel === t.id) + '"><span class="dot" style="width:10px;height:10px;background:' + (catColor(t.category)) + '"></span><span class="grow"><span class="strong">' + esc(t.description || t.occasion || "Gasto") + '</span><span class="meta">' + esc([t.occasion, fmtDate(t.date), state.cat ? "" : t.category].filter(Boolean).join(" · ")) + '</span></span><span class="strong">' + esc(clp(-t.amount)) + "</span></button></li>"
      ).join("") || '<li class="empty">No hay gastos ' + (state.cat ? "en esta categoría " : "") + "este mes.</li>";
      document.querySelectorAll("[data-tx]").forEach((b) => b.addEventListener("click", () => { state.sel = Number(b.dataset.tx); renderDetail(); loadListSel(); }));
      renderDetail();
    }
    function loadListSel() { document.querySelectorAll("[data-tx]").forEach((b) => b.setAttribute("aria-pressed", String(Number(b.dataset.tx) === state.sel))); }
    function renderDetail() {
      const t = state.items.find((x) => x.id === state.sel);
      const el = $("#g-detail");
      if (!t) { el.innerHTML = '<div class="empty" style="text-align:center;min-height:300px;display:flex;align-items:center;justify-content:center"><p>Toca un gasto para ver el detalle y cambiarle la categoría.</p></div>'; return; }
      const opts = (state.cats.indexOf(t.category) < 0 ? [t.category].concat(state.cats) : state.cats).map((c) => '<option value="' + esc(c) + '"' + (c === t.category ? " selected" : "") + ">" + esc(c) + "</option>").join("");
      el.innerHTML =
        "<h2>" + esc(t.description || t.occasion || "Gasto") + '</h2><p class="faint small" style="margin:4px 0 16px">' + esc(fmtDate(t.date)) + " · " + esc(clp(-t.amount)) + "</p>" +
        (t.has_receipt ? '<div class="receipt" role="img" aria-label="Boleta"><p style="text-align:center;font-weight:700">' + esc(t.merchant || "Boleta") + '</p><div class="line"><span>TOTAL</span><span>' + esc(clp(-t.amount)) + "</span></div></div>" : '<p class="faint small">Este gasto no tiene foto de boleta.</p>') +
        '<dl class="kv"><div><dt>Comercio</dt><dd>' + esc(t.merchant || "—") + "</dd></div><div><dt>Ocasión</dt><dd>" + esc(t.occasion || "—") + "</dd></div></dl>" +
        '<div class="field" style="margin-top:16px"><label for="recat">Categoría</label><select id="recat">' + opts + '</select></div><p class="faint small" style="margin-top:6px">Al cambiarla, la torta se actualiza.</p>' +
        '<div style="margin-top:16px"><button class="btn ghost" type="button" id="del-tx">Borrar gasto</button></div>';
      $("#recat").addEventListener("change", async (e) => {
        await api("PATCH", "/finanzas/movimientos/" + t.id, { category: e.target.value });
        state.cat = e.target.value; await loadSummary(); await loadList();
      });
      $("#del-tx").addEventListener("click", async () => {
        if (!window.confirm("¿Borrar este gasto? No se puede deshacer.")) return;
        await api("DELETE", "/finanzas/movimientos/" + t.id); state.sel = null; await loadSummary(); await loadList();
      });
    }
    async function pickCat(name) { state.cat = name; state.sel = null; await loadSummary(); await loadList(); }
    function renderNewCats() {
      $("#t-cats").innerHTML = state.cats.map((c) => '<button type="button" class="chip" data-c="' + esc(c) + '" aria-pressed="' + (state.newCat === c) + '"><span class="dot" style="width:10px;height:10px;background:' + (catColor(c)) + '"></span>' + esc(c) + "</button>").join("");
      document.querySelectorAll("[data-c]").forEach((b) => b.addEventListener("click", () => { state.newCat = b.dataset.c; renderNewCats(); updateSave(); }));
    }
    function updateSave() { $("#t-save").disabled = !(Number($("#t-amt").value) > 0 && state.newCat); }
    $("#t-amt").addEventListener("input", updateSave);
    $("#tx-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        await api("POST", "/finanzas/movimientos", { tipo: "gasto", amount: $("#t-amt").value, category: state.newCat, occasion: $("#t-occ").value, description: $("#t-desc").value });
        $("#tx-msg").innerHTML = box("ok-box", "Listo: el gasto quedó en " + state.newCat + " y la torta se actualizó.");
        state.cat = state.newCat; state.newCat = null; e.target.reset(); renderNewCats(); updateSave();
        await loadSummary(); await loadList();
      } catch (err) { $("#tx-msg").innerHTML = box("error-box", err.message); }
    });
    $("#g-all").addEventListener("click", () => { state.cat = null; state.sel = null; loadSummary(); loadList(); });
    // Mis categorías: activar/sacar las por defecto, agregar y sacar las propias
    function applyCats(r) {
      state.cats = r.categories;
      if (state.newCat && state.cats.indexOf(state.newCat) < 0) state.newCat = null;
      renderNewCats(); updateSave();
      $("#c-list").innerHTML = r.all.map((c) => {
        if (c.fixed) return '<span class="chip cat-fixed" title="Siempre disponible"><span class="dot" style="width:10px;height:10px;background:' + catColor(c.name) + '"></span>' + esc(c.name) + "</span>";
        const label = (c.active ? "Sacar " : "Usar ") + c.name;
        return '<button type="button" class="chip cat-toggle" data-cat="' + esc(c.name) + '" data-on="' + c.active + '" aria-pressed="' + c.active + '" aria-label="' + esc(label) + '"><span class="dot" style="width:10px;height:10px;background:' + catColor(c.name) + '"></span>' + esc(c.name) + '<span class="cat-x" aria-hidden="true">' + (c.active ? (c.default ? "✓" : "✕") : "+") + "</span></button>";
      }).join("");
      document.querySelectorAll("[data-cat]").forEach((b) => b.addEventListener("click", async () => {
        const on = b.dataset.on === "true";
        try { applyCats(await api("PUT", "/finanzas/categorias", { name: b.dataset.cat, active: !on })); $("#c-msg").innerHTML = ""; await loadSummary(); }
        catch (e) { $("#c-msg").innerHTML = box("error-box", e.message); }
      }));
    }
    $("#c-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await api("POST", "/finanzas/categorias", { name: $("#c-name").value });
        applyCats(r); $("#c-name").value = "";
        $("#c-msg").innerHTML = '<span class="up small">Listo: ' + esc(r.added) + " ya aparece para registrar gastos.</span>";
        await loadSummary();
      } catch (err) { $("#c-msg").innerHTML = box("error-box", err.message); }
    });
    try {
      applyCats(await api("GET", "/finanzas/categorias"));
      await loadSummary(); await loadList();
    } catch (e) { $("#g-stats").innerHTML = box("error-box", e.message); }
    void prevYM;
  }
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
  function fmtDate(iso) { if (!iso) return ""; const [y, m, d] = iso.split("-").map(Number); return d + " " + MONTHS[m - 1].slice(0, 3); void y; }

  // ---------- Ajustes ----------
  async function pageAjustes() {
    const KEYS = ["humor", "sarcasmo", "frecuencia_chistes", "nivel_conversador"];
    const st = {};
    function preview() {
      const en = window.FinmateI18n && window.FinmateI18n.get() === "en";
      let base = en ? "Your portfolio is worth USD 14,773 and you're up 14% on what you invested." : "Tu portafolio vale USD 14.773 y vas ganando 14% sobre lo invertido.";
      if (st.tono === "profesional") base = en ? "Your portfolio is valued at USD 14,773, with a cumulative gain of 14.3% over cost." : "Su portafolio se valoriza en USD 14.773, con una ganancia acumulada de 14,3% sobre el costo.";
      if (st.tono === "amigo") base = en ? "Your portfolio is doing well: it's worth USD 14,773 and you're up 14% since you started." : "Tu portafolio anda bien: vale USD 14.773 y vas arriba un 14% desde que empezaste.";
      let extra = "";
      if (st.humor >= 7 && st.frecuencia_chistes >= 5) extra = en ? " If it keeps this up, coffee's on me." : " Si sigue así, te invito yo el café.";
      else if (st.sarcasmo >= 7) extra = en ? " Not bad for someone who checks the app every five minutes." : " Nada mal para alguien que revisa la app cada cinco minutos.";
      if (st.nivel_conversador >= 7) extra += en ? " Want me to tell you what moved the most today?" : " ¿Quieres que te cuente qué movió más hoy?";
      if (st.nivel_conversador <= 2) base = base.split(/[,:]/)[0] + ".";
      $("#p-preview").textContent = base + extra;
    }
    document.addEventListener("finmate:lang", () => { if (st.tono) preview(); });
    function paintTono() { document.querySelectorAll("[data-tono]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.tono === st.tono))); }
    try {
      const p = await api("GET", "/personalidad");
      Object.assign(st, p);
      KEYS.forEach((k) => { const el = $("#p-" + k); el.value = p[k]; $("#v-" + k).textContent = p[k] + "/10"; el.addEventListener("input", () => { st[k] = Number(el.value); $("#v-" + k).textContent = el.value + "/10"; preview(); }); });
      paintTono(); preview();
    } catch (e) { $("#p-msg").innerHTML = box("error-box", e.message); }
    document.querySelectorAll("[data-tono]").forEach((b) => b.addEventListener("click", () => { st.tono = b.dataset.tono; paintTono(); preview(); }));
    $("#p-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { tono: st.tono }; KEYS.forEach((k) => { body[k] = Number(st[k]); });
      try { await api("PUT", "/personalidad", body); $("#p-msg").innerHTML = '<span class="up small">Guardado. El bot ya te habla así.</span>'; } catch (err) { $("#p-msg").innerHTML = box("error-box", err.message); }
    });

    let catalog = [];
    function renderFollows(s) {
      $("#s-temas").innerHTML = s.temas.map((t) => '<span class="tag-x">' + esc(t.valor) + ' <span class="faint small">' + esc(t.tipo) + '</span><button type="button" data-unf="' + esc(t.tipo) + "|" + esc(t.valor) + '" aria-label="Dejar de seguir ' + esc(t.valor) + '">✕</button></span>').join("") || '<span class="faint small">Ninguno</span>';
      $("#s-inds").innerHTML = s.indicadores.map((i) => '<span class="tag-x">' + esc(i.name) + '<button type="button" data-unf="indicador|' + esc(i.code) + '" aria-label="Dejar de seguir ' + esc(i.name) + '">✕</button></span>').join("") || '<span class="faint small">Ninguno</span>';
      document.querySelectorAll("[data-unf]").forEach((b) => b.addEventListener("click", async () => {
        const [tipo, ...rest] = b.dataset.unf.split("|");
        try { renderFollows(await api("DELETE", "/seguimientos", { tipo: tipo, valor: rest.join("|") })); } catch (e) { $("#s-msg").innerHTML = box("error-box", e.message); }
      }));
    }
    function renderValueField() {
      const wrap = $("#s-valor-wrap");
      if ($("#s-tipo").value === "indicador") {
        wrap.innerHTML = '<label for="s-valor">Qué seguir</label><select id="s-valor">' + catalog.map((c) => '<option value="' + esc(c.code) + '">' + esc(c.name) + "</option>").join("") + "</select>";
      } else {
        wrap.innerHTML = '<label for="s-valor">Qué seguir</label><input id="s-valor" maxlength="200" required placeholder="Ej: bancos regionales">';
      }
    }
    try {
      const s = await api("GET", "/seguimientos"); catalog = s.catalogo; renderFollows(s); renderValueField();
    } catch (e) { $("#s-msg").innerHTML = box("error-box", e.message); }
    $("#s-tipo").addEventListener("change", renderValueField);
    $("#s-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { renderFollows(await api("POST", "/seguimientos", { tipo: $("#s-tipo").value, valor: $("#s-valor").value })); $("#s-msg").innerHTML = ""; if ($("#s-valor").tagName === "INPUT") $("#s-valor").value = ""; } catch (err) { $("#s-msg").innerHTML = box("error-box", err.message); }
    });

    try {
      const a = await api("GET", "/avisos");
      $("#a-thr").value = a.watchlist_threshold_pct; $("#a-weekly").checked = a.weekly_summary_enabled;
      if ($("#a-news")) $("#a-news").value = a.news_max_per_day;
      if ($("#a-earn")) $("#a-earn").value = a.earnings_alerts || "mine";
      if ($("#a-macro")) $("#a-macro").checked = !!a.macro_alerts;
      if ($("#a-mnews")) $("#a-mnews").checked = !!a.market_news_alerts;
    } catch (e) { $("#a-msg").innerHTML = box("error-box", e.message); }
    $("#a-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { watchlist_threshold_pct: $("#a-thr").value, weekly_summary_enabled: $("#a-weekly").checked };
      if ($("#a-news")) body.news_max_per_day = parseInt($("#a-news").value || "0", 10);
      if ($("#a-earn")) body.earnings_alerts = $("#a-earn").value;
      if ($("#a-macro")) body.macro_alerts = $("#a-macro").checked;
      if ($("#a-mnews")) body.market_news_alerts = $("#a-mnews").checked;
      try { await api("PUT", "/avisos", body); $("#a-msg").innerHTML = '<span class="up small">Avisos guardados.</span>'; } catch (err) { $("#a-msg").innerHTML = box("error-box", err.message); }
    });
  }

  // ---------- Acceso: código por WhatsApp (o modo desarrollo) ----------
  function pageAcceso() {
    const dev = $("#dev-login");
    if (dev) {
      dev.addEventListener("submit", async (e) => {
        e.preventDefault();
        try { await api("POST", "/auth/dev-login", { phone: $("#phone").value }); location.href = "/panel/"; } catch (err) { $("#login-msg").innerHTML = box("error-box", err.message); }
      });
      return;
    }
    const req = $("#code-request"), ver = $("#code-verify"), msg = $("#login-msg");
    if (!req) return;
    req.addEventListener("submit", async (e) => {
      e.preventDefault();
      msg.innerHTML = "";
      const btn = req.querySelector("button"); btn.disabled = true;
      try {
        const r = await api("POST", "/auth/request-code", { phone: $("#phone").value });
        req.style.display = "none"; ver.style.display = "flex";
        msg.innerHTML = '<span class="up small">Te mandamos el código al WhatsApp ' + (r.phone || "") + ".</span>";
        $("#code").focus();
      } catch (err) { msg.innerHTML = box("error-box", err.message); }
      btn.disabled = false;
    });
    ver.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("POST", "/auth/verify-code", { phone: $("#phone").value, code: $("#code").value }); location.href = "/panel/"; }
      catch (err) { msg.innerHTML = box("error-box", err.message); }
    });
    $("#code-back").addEventListener("click", () => { ver.style.display = "none"; req.style.display = "flex"; msg.innerHTML = ""; });
  }


  // ---------- celular: pestañas abajo y deslizar entre pestañas ----------
  // Las 5 pestañas están en la misma página, lado a lado (base.html). Al
  // arrastrar, el riel sigue al dedo y la pestaña vecina ya se ve; al soltar,
  // termina de deslizarse sin recargar nada (como Instagram). La URL se
  // actualiza con history.pushState, así "atrás" y recargar siguen funcionando.
  function initTabs(modules) {
    const rail = $(".rail"); const track = document.getElementById("track"); const main = document.getElementById("main");
    if (!rail || !track || !main) return;
    const links = Array.from(rail.querySelectorAll("a"));
    const panes = Array.from(track.querySelectorAll(".pane"));
    const names = panes.map((p) => p.dataset.pane);
    const pill = rail.querySelector(".tab-pill");
    const mq = window.matchMedia("(max-width: 760px)");
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const EASE = "cubic-bezier(.22,.8,.24,1)";
    let idx = names.indexOf(document.body.dataset.page);
    if (idx < 0) return;
    const started = new Set([names[idx]]);

    function startPane(i) {
      const n = names[i];
      if (!n || started.has(n)) return;
      started.add(n);
      try { (modules[n] || function () {})(); } catch (e) { /* cada pestaña maneja sus errores */ }
    }
    const width = () => track.parentElement.clientWidth;
    function setTrack(px, ms) {
      track.style.transition = ms ? "transform " + ms + "ms " + EASE : "none";
      track.style.transform = "translate3d(" + px + "px,0,0)";
    }
    function placePill(frac, ms) {
      if (!pill || !mq.matches) return;
      const cur = links[idx]; const n = links[idx + (frac > 0 ? 1 : -1)];
      let left = cur.offsetLeft, w = cur.offsetWidth;
      if (n && frac) { const f = Math.min(Math.abs(frac), 1); left += (n.offsetLeft - cur.offsetLeft) * f; w += (n.offsetWidth - cur.offsetWidth) * f; }
      pill.style.transition = ms === 0 ? "none" : "";
      pill.style.transform = "translateX(" + left + "px)"; pill.style.width = w + "px";
      const near = n && Math.abs(frac) > 0.5 ? n : cur;
      links.forEach((a) => a.classList.toggle("lit", a === near));
    }
    // Las pestañas vecinas se alinean con lo que el usuario está viendo
    // (si bajó en la página, la vecina se muestra desde arriba igual).
    function alignNeighbors(on) {
      const y = on ? window.scrollY : 0;
      panes.forEach((p, i) => { if (i !== idx) p.style.transform = y ? "translateY(" + y + "px)" : ""; });
    }
    function markActive() {
      panes.forEach((p, i) => {
        const on = i === idx;
        p.classList.toggle("active", on);
        if (on) { p.removeAttribute("aria-hidden"); p.inert = false; } else { p.setAttribute("aria-hidden", "true"); p.inert = true; }
      });
      links.forEach((a, i) => { if (i === idx) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      document.body.dataset.page = names[idx];
      document.title = "Finmate — " + (links[idx].getAttribute("title") || "");
    }
    function goTo(i, opts) {
      opts = opts || {};
      if (i < 0 || i >= panes.length) return;
      const ms = calm || opts.instant ? 0 : (opts.ms || 300);
      if (i === idx) { setTrack(-idx * width(), ms); placePill(0); return; }
      startPane(i);
      alignNeighbors(true);
      idx = i;
      placePill(0);
      setTrack(-idx * width(), ms);
      const finish = () => {
        markActive();
        document.dispatchEvent(new Event("finmate:pane"));
        alignNeighbors(false);
        window.scrollTo(0, 0);
        track.style.transition = "none";
      };
      if (ms) setTimeout(finish, ms + 20); else finish();
      if (opts.push !== false && links[idx].href !== location.href) {
        try { history.pushState({ pane: names[idx] }, "", links[idx].href); } catch (e) {}
      }
      // Precarga los datos de las vecinas para que se vean al deslizar
      setTimeout(() => { startPane(idx - 1); startPane(idx + 1); }, ms + 150);
    }

    function layout() {
      if (mq.matches) { setTrack(-idx * width(), 0); placePill(0, 0); }
      else { track.style.transform = ""; track.style.transition = ""; }
    }
    markActive(); layout();
    window.addEventListener("resize", layout);
    mq.addEventListener ? mq.addEventListener("change", layout) : mq.addListener(layout);
    window.addEventListener("popstate", () => {
      const i = links.findIndex((a) => a.href === location.href || a.pathname === location.pathname);
      if (i >= 0 && mq.matches) goTo(i, { push: false }); else if (i >= 0) location.reload();
    });
    // Precarga las vecinas apenas termina de cargar la pestaña actual
    setTimeout(() => { if (mq.matches) { startPane(idx - 1); startPane(idx + 1); } }, 600);

    // Tocar una pestaña desliza sin recargar (en computador navega normal)
    links.forEach((a, i) => a.addEventListener("click", (e) => {
      if (!mq.matches || e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      goTo(i, { ms: Math.min(260 + 60 * Math.abs(i - idx), 420) });
    }));

    // Arrastrar con el dedo
    function scrollsX(el) {
      for (; el && el !== main; el = el.parentElement) {
        const ox = getComputedStyle(el).overflowX;
        if ((ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 2) return true;
      }
      return false;
    }
    let sx = 0, sy = 0, lastX = 0, lastT = 0, vx = 0, dx = 0, lock = null, on = false;
    main.addEventListener("touchstart", (e) => {
      on = false;
      if (!mq.matches || e.touches.length !== 1) return;
      const t = e.target;
      if (t.closest("input, textarea, select, [data-noswipe]") || scrollsX(t)) return;
      on = true; lock = null; dx = 0; vx = 0;
      sx = lastX = e.touches[0].clientX; sy = e.touches[0].clientY; lastT = performance.now();
    }, { passive: true });
    main.addEventListener("touchmove", (e) => {
      if (!on) return;
      const x = e.touches[0].clientX, mx = x - sx, my = e.touches[0].clientY - sy;
      if (lock === null) {
        if (Math.abs(mx) < 8 && Math.abs(my) < 8) return;
        lock = Math.abs(mx) > Math.abs(my) * 1.2 ? "x" : "y";
        if (lock === "x") { alignNeighbors(true); startPane(idx - 1); startPane(idx + 1); rail.classList.add("dragging"); }
      }
      if (lock !== "x") return;
      e.preventDefault();
      const now = performance.now();
      vx = 0.8 * ((x - lastX) / Math.max(now - lastT, 1)) + 0.2 * vx;  // px/ms suavizado
      lastX = x; lastT = now;
      const atEdge = (mx > 0 && idx === 0) || (mx < 0 && idx === panes.length - 1);
      dx = atEdge ? mx / 3 : mx;   // resistencia en los extremos
      setTrack(-idx * width() + dx, 0);
      placePill(atEdge ? 0 : -dx / width(), 0);
    }, { passive: false });
    function end() {
      if (!on) return; on = false;
      rail.classList.remove("dragging");
      if (lock !== "x") return;
      const w = width();
      const flick = Math.abs(vx) > 0.35;
      let target = idx;
      if (flick) target = idx + (vx < 0 ? 1 : -1);
      else if (Math.abs(dx) > w * 0.35) target = idx + (dx < 0 ? 1 : -1);
      target = Math.max(0, Math.min(panes.length - 1, target));
      // La duración sigue la velocidad del dedo: un gesto rápido termina rápido
      const remaining = Math.abs(-target * w - (-idx * w + dx));
      const ms = Math.round(Math.max(160, Math.min(340, flick ? remaining / Math.abs(vx) : remaining * 0.9)));
      if (target !== idx) goTo(target, { ms: ms });
      else { setTrack(-idx * w, ms); placePill(0); setTimeout(() => alignNeighbors(false), ms + 20); }
    }
    main.addEventListener("touchend", end);
    main.addEventListener("touchcancel", end);
  }

  // ---------- celular: la barra de abajo se esconde al bajar y vuelve al subir ----------
  function initAutoHideRail() {
    const rail = $(".rail"); if (!rail) return;
    const mq = window.matchMedia("(max-width: 760px)");
    let lastY = window.scrollY, acc = 0, ticking = false;
    function update() {
      ticking = false;
      const y = Math.max(window.scrollY, 0);
      const dy = y - lastY; lastY = y;
      if (!mq.matches) { rail.classList.remove("rail-hidden"); return; }
      // cerca del inicio o del final de la página, siempre visible
      const nearBottom = window.innerHeight + y >= document.documentElement.scrollHeight - 40;
      if (y < 60 || nearBottom) { acc = 0; rail.classList.remove("rail-hidden"); return; }
      acc = (acc > 0) === (dy > 0) ? acc + dy : dy;   // suma solo en la misma dirección
      if (acc > 24) rail.classList.add("rail-hidden");
      else if (acc < -12) rail.classList.remove("rail-hidden");
    }
    window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    // Al cambiar de pestaña o tocar un campo, la barra vuelve
    document.addEventListener("finmate:pane", () => { acc = 0; lastY = window.scrollY; rail.classList.remove("rail-hidden"); });
  }

  // ---------- celular: evitar el zoom accidental ----------
  // iOS ignora user-scalable=no en Safari, así que también se bloquea el
  // gesto de pellizcar y el doble toque (además, los campos usan 16px para
  // que iOS no haga zoom al tocarlos; ver panel.css).
  function preventZoom() {
    ["gesturestart", "gesturechange", "gestureend"].forEach((ev) => document.addEventListener(ev, (e) => e.preventDefault(), { passive: false }));
    document.addEventListener("touchmove", (e) => { if (e.touches.length > 1) e.preventDefault(); }, { passive: false });
    let lastTap = 0;
    document.addEventListener("touchend", (e) => {
      const now = Date.now();
      if (now - lastTap < 300 && !e.target.closest("input, textarea, select")) e.preventDefault();
      lastTap = now;
    }, { passive: false });
  }

  // ---------- feedback ----------
  function pageFeedback() {
    const st = { tipo: null, rating: null };
    const text = $("#fb-text"), send = $("#fb-send"), out = $("#fb-out");
    function refresh() {
      $("#fb-count").textContent = text.value.length + "/2000";
      send.disabled = !(st.tipo && text.value.trim().length >= 5);
    }
    function group(sel, key, attr) {
      document.querySelectorAll(sel + " [data-" + attr + "]").forEach((b) => b.addEventListener("click", () => {
        const v = b.dataset[attr]; st[key] = st[key] === v && key === "rating" ? null : v;
        document.querySelectorAll(sel + " [data-" + attr + "]").forEach((x) => x.setAttribute("aria-pressed", String(x.dataset[attr] === st[key])));
        refresh();
      }));
    }
    group("#fb-tipo", "tipo", "tipo"); group("#fb-rating", "rating", "rating");
    text.addEventListener("input", refresh); refresh();
    $("#fb-form").addEventListener("submit", async (e) => {
      e.preventDefault(); if (send.disabled) return;
      send.disabled = true; out.innerHTML = '<span class="faint small">Enviando…</span>';
      try {
        await api("POST", "/feedback", { tipo: st.tipo, rating: st.rating ? Number(st.rating) : null, message: text.value.trim(), contact: $("#fb-contact").checked });
        out.innerHTML = '<span class="up small">¡Gracias! Tu mensaje ya le llegó al equipo de Finmate.</span>';
        text.value = ""; st.tipo = null; st.rating = null; $("#fb-contact").checked = false;
        document.querySelectorAll("#fb-form [aria-pressed]").forEach((x) => x.setAttribute("aria-pressed", "false"));
        refresh();
      } catch (err) { out.innerHTML = box("error-box", err.message); refresh(); }
    });
  }

  const page = document.body.dataset.page;
  const MODULES = { resumen: pageResumen, inversiones: pageInversiones, gastos: pageGastos, ajustes: pageAjustes, feedback: pageFeedback };
  preventZoom();
  if (page === "acceso") pageAcceso();
  else { initShell(); initLang(); (MODULES[page] || function () {})(); initTabs(MODULES); initAutoHideRail(); }
})();
