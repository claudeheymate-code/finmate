/* Finmate — panel de administrador. */
(function () {
  "use strict";
  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => Array.from((el || document).querySelectorAll(s));
  const esc = (v) => String(v == null ? "" : v).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const box = (cls, msg) => `<div class="${cls}">${esc(msg)}</div>`;
  const okMsg = (msg) => `<span class="up small">${esc(msg)}</span>`;
  const page = document.body.dataset.page || "";

  async function api(method, path, body) {
    const opts = { method, headers: { "X-Finmate": "1" }, credentials: "same-origin" };
    if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), path.includes("probar") || path.includes("chequear") ? 60000 : 20000);
    opts.signal = ctrl.signal;
    let r;
    try { r = await fetch("/admin/api" + path, opts); }
    catch (e) { throw new Error(e.name === "AbortError" ? "El servidor está tardando más de lo normal. Intenta de nuevo." : "Sin conexión."); }
    finally { clearTimeout(timer); }
    if (r.status === 401 && page !== "admin-login") { location.href = "/admin/login"; throw new Error("no_autenticado"); }
    let data = {};
    try { data = await r.json(); } catch (e) { /* sin cuerpo */ }
    if (!r.ok) throw new Error(data.error || ("Error " + r.status));
    if (method === "GET") cachePut(path, data);
    else cacheClear();   // algo cambió (aprobar, revisar, guardar): lo guardado ya no sirve
    return data;
  }

  // ---------- datos al instante ----------
  // Cada pestaña del admin es una página aparte. Para que no quede "Cargando…"
  // 1-3 s al cambiar, se guarda lo último que llegó de cada consulta (solo en
  // esta sesión del navegador) y se muestra de inmediato mientras llega lo nuevo.
  const CK = "fm-admin:";
  function cachePut(path, data) { try { sessionStorage.setItem(CK + path, JSON.stringify({ t: Date.now(), d: data })); } catch (e) { /* sin espacio o modo privado */ } }
  function cacheGet(path) { try { return JSON.parse(sessionStorage.getItem(CK + path) || "null"); } catch (e) { return null; } }
  function cacheClear() { try { Object.keys(sessionStorage).filter((k) => k.startsWith(CK)).forEach((k) => sessionStorage.removeItem(k)); } catch (e) {} }
  // Muestra lo guardado (si hay) y después lo nuevo, solo si cambió.
  async function live(path, render, onError) {
    const c = cacheGet(path);
    let shown = null;
    if (c) { try { render(c.d, true); shown = JSON.stringify(c.d); } catch (e) { shown = null; } }
    try {
      const d = await api("GET", path);
      if (JSON.stringify(d) !== shown) render(d, false);
    } catch (e) { if (shown === null && onError) onError(e); }
  }
  // Con la página ya lista, trae en segundo plano los datos de las otras pestañas
  const PRELOAD = ["/badge", "/resumen", "/usuarios", "/inbox", "/seguridad", "/anuncios", "/fuentes"];
  function preloadOthers() {
    const later = window.requestIdleCallback || ((f) => setTimeout(f, 300));
    setTimeout(() => later(async () => {
      for (const p of PRELOAD) {
        const c = cacheGet(p);
        if (c && Date.now() - c.t < 60000) continue;
        try { await api("GET", p); } catch (e) { return; }
      }
    }), 1200);
  }

  const fmtDate = (iso, withTime) => {
    if (!iso) return "—";
    const d = new Date(iso + (iso.endsWith("Z") || iso.includes("+") ? "" : "Z"));
    const opts = withTime ? { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" } : { day: "numeric", month: "short", year: "numeric" };
    return d.toLocaleString("es-CL", opts);
  };
  const ago = (iso) => {
    if (!iso) return "nunca";
    const d = new Date(iso + (iso.endsWith("Z") || iso.includes("+") ? "" : "Z"));
    const m = Math.round((Date.now() - d.getTime()) / 60000);
    if (m < 1) return "recién"; if (m < 60) return `hace ${m} min`;
    const h = Math.round(m / 60); if (h < 24) return `hace ${h} h`;
    const days = Math.round(h / 24); return days < 30 ? `hace ${days} d` : fmtDate(iso);
  };
  const money = (v, cur) => {
    if (v == null) return "—";
    if (cur === "CLP") return "$" + Math.round(v).toLocaleString("es-CL") + " CLP";
    return "US$" + Number(v).toLocaleString("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: v < 1 && v > 0 ? 4 : 2 });
  };
  const num = (v) => (v == null ? "—" : Number(v).toLocaleString("es-CL"));
  const STATUS = { approved: ["ok", "Con acceso"], pending: ["wait", "Pendiente"], denied: ["no", "Rechazado"] };
  const stPill = (s) => { const [c, t] = STATUS[s] || ["muted", s]; return `<span class="st ${c}">${t}</span>`; };

  // ---------- Común ----------
  function initCommon() {
    const out = $("#logout");
    if (out) out.addEventListener("click", async () => { cacheClear(); try { await api("POST", "/logout"); } catch (e) {} location.href = "/admin/login"; });
    const badge = $("#inbox-badge");
    if (badge) live("/badge", (d) => {
      const n = d.total || 0;
      badge.textContent = n > 99 ? "99+" : n; badge.hidden = !(n > 0);
    });
    preloadOthers();
  }

  // ---------- Login ----------
  function pageLogin() {
    cacheClear();
    const f = $("#admin-dev-login"); if (!f) return;
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      try { await api("POST", "/dev-login", { email: $("#admin-email").value }); location.href = "/admin/"; }
      catch (err) { $("#login-msg").innerHTML = box("error-box", err.message); }
    });
  }

  // ---------- Costos ----------
  let SUBS = [];
  function renderCostos(d) {
    SUBS = d.subscriptions || [];
    const fx = d.monthly_fixed || {};
    $("#st-fixed").textContent = money(fx.USD, "USD");
    $("#st-fixed-sub").textContent = fx.CLP ? "+ " + money(fx.CLP, "CLP") + " · sin contar prepagos ni uso" : "Sin contar prepagos ni consumo por uso";
    const u = d.usage || {};
    $("#st-claude").textContent = money(u.claude_cost_usd, "USD");
    const calls = (u.claude || []).reduce((a, m) => a + (m.calls || 0), 0);
    $("#st-claude-sub").textContent = `${num(calls)} respuestas del modelo${u.claude_cost_complete === false ? " · falta precio de algún modelo" : ""}`;
    const wa = u.whatsapp || {};
    $("#st-wa").textContent = num((wa.text || 0) + (wa.template || 0)) + " msj";
    $("#st-wa-sub").textContent = `${num(wa.template || 0)} con plantilla (se cobran)${wa.cost_usd != null ? " · " + money(wa.cost_usd, "USD") : ""}`;
    const us = d.users || {};
    $("#st-users").textContent = num(us.approved);
    $("#st-users-sub").textContent = `${num(us.active_7d)} activos en 7 días · ${num(us.pending)} pendientes`;
    renderSubs(d.monthly_fixed);
    renderUsage(u);
  }

  function renderSubs() {
    const tb = $("#sub-rows"); if (!tb) return;
    if (!SUBS.length) { tb.innerHTML = '<tr><td colspan="6" class="empty">No hay suscripciones. Agrega la primera.</td></tr>'; return; }
    tb.innerHTML = SUBS.map((s) => `<tr class="clickable" data-id="${esc(s.id)}">
      <td><p class="cell-title">${esc(s.name)}${s.essential ? '<span class="ess">esencial</span>' : ""}</p><p class="cell-sub">${esc(s.detail)}</p></td>
      <td class="nowrap" data-label="Ciclo">${esc(s.cycle)}</td>
      <td class="r" data-label="Costo">${s.cycle === "gratis" ? "Gratis" : money(s.cost, s.currency)}</td>
      <td class="nowrap" data-label="Renueva">${s.renews_on ? fmtDate(s.renews_on) : "—"}</td>
      <td class="hide-sm"><span class="cell-sub">${esc(s.notes)}</span></td>
      <td class="r">${s.url ? `<a href="${esc(s.url)}" target="_blank" rel="noopener">Facturación ↗</a>` : ""}</td></tr>`).join("");
    $$("tr.clickable", tb).forEach((tr) => tr.addEventListener("click", (e) => {
      if (e.target.closest("a")) return;   // el link de facturación abre su página, no el formulario
      openSubForm(SUBS.find((s) => s.id === tr.dataset.id));
    }));
  }

  function openSubForm(s) {
    const f = $("#sub-form"); f.hidden = false;
    s = s || { id: "", name: "", detail: "", cost: 0, currency: "USD", cycle: "mensual", renews_on: "", url: "", notes: "", essential: false };
    $("#sf-id").value = s.id || ""; $("#sf-name").value = s.name; $("#sf-detail").value = s.detail || "";
    $("#sf-cost").value = s.cost; $("#sf-currency").value = s.currency; $("#sf-cycle").value = s.cycle;
    $("#sf-renews").value = s.renews_on || ""; $("#sf-url").value = s.url || ""; $("#sf-notes").value = s.notes || "";
    $("#sf-essential").checked = !!s.essential; $("#sf-delete").hidden = !s.id; $("#sf-msg").innerHTML = "";
    f.scrollIntoView({ behavior: "smooth", block: "center" }); $("#sf-name").focus();
  }

  function renderUsage(u) {
    if ($("#u-month")) $("#u-month").textContent = `Mes ${u.month || ""}: lo que el bot usó de Claude y de WhatsApp.`;
    const tb = $("#u-claude");
    if (tb) {
      const rows = u.claude || [];
      tb.innerHTML = rows.length ? rows.map((m) => `<tr>
        <td class="nowrap"><span class="cell-title">${esc(m.model)}</span></td>
        <td class="r" data-label="Respuestas">${num(m.calls)}</td><td class="r" data-label="Tokens entrada">${num(m.input_tokens)}</td><td class="r" data-label="Tokens salida">${num(m.output_tokens)}</td>
        <td class="r nowrap" data-label="Precio US$/M (entrada / salida)"><input class="price-in" data-model="${esc(m.model)}" data-k="in" type="number" min="0" step="0.01" value="${m.price_in ?? ""}" aria-label="Precio entrada"> /
          <input class="price-in" data-model="${esc(m.model)}" data-k="out" type="number" min="0" step="0.01" value="${m.price_out ?? ""}" aria-label="Precio salida"></td>
        <td class="r" data-label="Costo">${m.cost_usd == null ? '<span class="faint">falta precio</span>' : money(m.cost_usd, "USD")}</td></tr>`).join("")
        : '<tr><td colspan="6" class="empty">Todavía no hay consumo registrado este mes.</td></tr>';
      $$(".price-in", tb).forEach((inp) => inp.addEventListener("change", async () => {
        const model = inp.dataset.model;
        const pin = $(`.price-in[data-model="${model}"][data-k="in"]`, tb).value, pout = $(`.price-in[data-model="${model}"][data-k="out"]`, tb).value;
        if (pin === "" || pout === "") return;
        try { renderUsage(await api("PUT", "/precios", { model, in: pin, out: pout })); } catch (e) { alertBox(e.message); }
      }));
    }
    const wa = u.whatsapp || {};
    const ul = $("#u-wa");
    if (ul) ul.innerHTML = `
      <li><div class="grow"><p class="strong">Respuestas y mensajes de texto</p><p class="faint small">Gratis dentro de las 24 h desde que el usuario escribió</p></div><span class="num">${num(wa.text)}</span></li>
      <li><div class="grow"><p class="strong">Avisos con plantilla</p><p class="faint small">Los que inicia el bot fuera de la ventana de 24 h; Meta los cobra</p></div><span class="num">${num(wa.template)}${wa.cost_usd != null ? " · " + money(wa.cost_usd, "USD") : ""}</span></li>
      <li><div class="grow"><p class="strong">Fallidos</p><p class="faint small">Mensajes que Meta rechazó</p></div><span class="num ${wa.failed ? "down" : ""}">${num(wa.failed)}</span></li>`;
    const wp = $("#wa-price-in"); if (wp && wa.template_price_usd != null && document.activeElement !== wp) wp.value = wa.template_price_usd;
  }

  function alertBox(msg) { const m = $("#sf-msg") || $("#us-msg"); if (m) m.innerHTML = box("error-box", msg); }

  function pageCostos() {
    $("#sub-add").addEventListener("click", () => openSubForm(null));
    $("#sf-cancel").addEventListener("click", () => { $("#sub-form").hidden = true; });
    $("#sub-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const body = { id: $("#sf-id").value || undefined, name: $("#sf-name").value, detail: $("#sf-detail").value, cost: $("#sf-cost").value,
        currency: $("#sf-currency").value, cycle: $("#sf-cycle").value, renews_on: $("#sf-renews").value, url: $("#sf-url").value,
        notes: $("#sf-notes").value, essential: $("#sf-essential").checked };
      try { const d = await api("POST", "/suscripciones", body); SUBS = d.subscriptions; renderSubs(); $("#sub-form").hidden = true; refreshStats(); }
      catch (err) { $("#sf-msg").innerHTML = box("error-box", err.message); }
    });
    $("#sf-delete").addEventListener("click", async () => {
      const id = $("#sf-id").value; if (!id) return;
      try { const d = await api("DELETE", "/suscripciones/" + encodeURIComponent(id)); SUBS = d.subscriptions; renderSubs(); $("#sub-form").hidden = true; refreshStats(); }
      catch (err) { $("#sf-msg").innerHTML = box("error-box", err.message); }
    });
    $("#wa-price").addEventListener("submit", async (e) => {
      e.preventDefault();
      try { renderUsage(await api("PUT", "/precios", { whatsapp_template_usd: $("#wa-price-in").value })); $("#wa-msg").innerHTML = okMsg("Guardado."); }
      catch (err) { $("#wa-msg").innerHTML = box("error-box", err.message); }
    });
  }
  async function refreshStats() { try { renderCostos(await api("GET", "/resumen")); } catch (e) {} }

  // ---------- Usuarios ----------
  let USERS = [], UFILTER = "all";
  function renderUsers() {
    const q = ($("#us-q").value || "").toLowerCase();
    const rows = USERS.filter((u) => (UFILTER === "all" || u.status === UFILTER) && (!q || (u.name + " " + u.phone + " " + (u.email || "")).toLowerCase().includes(q)));
    const tb = $("#us-rows");
    tb.innerHTML = rows.length ? rows.map((u) => `<tr>
      <td><p class="cell-title">${esc(u.name || "Sin nombre")}</p>${u.email ? `<p class="cell-sub"><a href="mailto:${esc(u.email)}">${esc(u.email)}</a></p>` : '<p class="cell-sub faint">Sin correo</p>'}</td>
      <td class="nowrap" data-label="WhatsApp">+${esc(u.phone.replace(/^\+/, ""))}</td>
      <td class="nowrap hide-sm" data-label="Inicio">${fmtDate(u.created_at)}</td>
      <td class="nowrap" data-label="Último mensaje" title="${esc(fmtDate(u.last_message_at, true))}">${ago(u.last_message_at)}${u.status === "approved" ? (u.window_open
        ? ' <span class="st ok" title="Escribió en las últimas 24 h: el bot puede mandarle avisos y resúmenes">24 h</span>'
        : ' <span class="st wait" title="No escribe hace más de 24 h: WhatsApp no deja mandarle nada hasta que escriba. Sus resúmenes y avisos se guardan y le llegan cuando vuelva a escribir.">Ventana cerrada</span>') : ""}</td>
      <td class="r" data-label="Mensajes" title="Este mes: ${num(u.month_messages)}">${num(u.messages)}<p class="cell-sub">${num(u.month_messages)} este mes</p></td>
      <td class="r nowrap" data-label="Costo del mes" title="Claude ${esc(money(u.cost_claude_usd, "USD"))} · WhatsApp ${esc(money(u.cost_whatsapp_usd, "USD"))} (${num(u.templates)} plantillas) · ${num(u.bot_messages)} mensajes del bot">${money(u.cost_usd, "USD")}${u.cost_per_message_usd != null ? `<p class="cell-sub">${money(u.cost_per_message_usd, "USD")} por mensaje</p>` : ""}</td>
      <td class="r hide-sm">${num(u.watchlist)}</td><td class="r hide-sm">${num(u.portfolio)}</td>
      <td data-label="Acceso">${stPill(u.status)}</td>
      <td><div class="row-actions">${actionButtons(u)}</div></td></tr>`).join("")
      : '<tr><td colspan="10" class="empty">No hay usuarios con ese filtro.</td></tr>';
    bindAccess(tb, loadUsers, "#us-msg");
  }
  function actionButtons(u) {
    if (u.status === "approved") return `<button class="btn ghost sm danger" data-uid="${u.id}" data-act="deny">Quitar acceso</button>`;
    if (u.status === "pending") return `<button class="btn sm" data-uid="${u.id}" data-act="approve">Aprobar</button><button class="btn ghost sm danger" data-uid="${u.id}" data-act="deny">Rechazar</button>`;
    return `<button class="btn ghost sm" data-uid="${u.id}" data-act="approve">Dar acceso</button>`;
  }
  function bindAccess(root, reload, msgSel) {
    $$("button[data-act]", root).forEach((b) => b.addEventListener("click", async () => {
      b.disabled = true;
      try {
        const r = await api("POST", `/usuarios/${b.dataset.uid}/acceso`, { action: b.dataset.act });
        let msg = r.status === "approved" ? "Acceso aprobado." : r.status === "denied" ? "Acceso rechazado." : "Listo.";
        if (r.status === "approved") msg += r.notified ? " Se le avisó por WhatsApp." : " No se pudo avisar por WhatsApp (pasaron más de 24 h desde su último mensaje); se enterará cuando vuelva a escribir.";
        $(msgSel).innerHTML = okMsg(msg);
        await reload();
      } catch (e) { $(msgSel).innerHTML = box("error-box", e.message); b.disabled = false; }
    }));
  }
  async function loadUsers() { showUsers(await api("GET", "/usuarios")); }
  function showUsers(d) {
    USERS = d.users || [];
    const c = d.counts || {};
    $("#us-approved").textContent = num(c.approved); $("#us-active").textContent = num(c.active_7d);
    $("#us-pending").textContent = num(c.pending); $("#us-msgs").textContent = num(c.messages);
    renderCosts(d.costs);
    renderUsers();
  }
  function renderCosts(k) {
    if (!k || !$("#us-tiers")) return;
    $("#us-tiers").innerHTML = k.tiers.map((t) => `<div class="tier">
      <p class="label">${esc(t.label)} <span class="faint">· ${esc(t.range)} mensajes al mes</span></p>
      <p class="value num">${t.projected_usd != null ? money(t.projected_usd, "USD") : "—"}<span class="faint small"> /mes</span></p>
      <p class="faint small">Estimado para ~${num(t.typical_messages)} mensajes al mes</p>
      <p class="small" style="margin-top:8px">${t.users ? `${num(t.users)} ${t.users === 1 ? "usuario" : "usuarios"} hoy · promedio real ${money(t.avg_cost_usd, "USD")} con ${num(t.avg_messages)} mensajes` : '<span class="faint">Nadie en este nivel todavía</span>'}</p>
    </div>`).join("");
    const since = k.tracking_since ? fmtDate(k.tracking_since, true) : "hoy";
    $("#us-costs-note").textContent = `Mes ${k.month}: ${money(k.month_total_usd, "USD")} en total por ${num(k.month_messages)} mensajes de usuarios`
      + (k.avg_cost_per_message_usd != null ? ` (≈ ${money(k.avg_cost_per_message_usd, "USD")} por mensaje, incluye resúmenes y avisos).` : ".")
      + ` El costo de cada usuario se mide desde ${since}; lo anterior solo entra en el total y en el estimado.`
      + (k.missing_price ? " Falta el precio de algún modelo o de las plantillas en Costos: esos montos no están sumados." : "");
  }
  function pageUsuarios() {
    $("#us-q").addEventListener("input", renderUsers);
    $$("#us-filter .chip").forEach((ch) => ch.addEventListener("click", () => {
      $$("#us-filter .chip").forEach((x) => x.setAttribute("aria-pressed", "false")); ch.setAttribute("aria-pressed", "true");
      UFILTER = ch.dataset.f; renderUsers();
    }));
    live("/usuarios", showUsers, (e) => { $("#us-rows").innerHTML = `<tr><td colspan="10">${box("error-box", e.message)}</td></tr>`; });
  }

  // ---------- Inbox ----------
  let FB = [], FFILTER = "open";
  const TIPOS = { idea: "Idea", problema: "Problema", me_gusta: "Me gusta", otro: "Otro" };
  function renderRequests(reqs) {
    const ul = $("#ib-req");
    const pend = reqs.filter((r) => r.status === "pending"), den = reqs.filter((r) => r.status === "denied");
    if (!reqs.length) { ul.innerHTML = '<li class="empty">No hay solicitudes. Cuando un número nuevo le escriba a Finmate, aparecerá aquí.</li>'; return; }
    const item = (r) => `<li><div class="inbox-item">
        <p class="strong">${esc(r.name || "Sin nombre")} <span class="faint">· +${esc(r.phone.replace(/^\+/, ""))}</span></p>
        ${r.email ? `<p class="small"><a href="mailto:${esc(r.email)}">${esc(r.email)}</a></p>` : ""}
        <div class="meta">${stPill(r.status)}${r.registered ? "" : '<span class="st muted">Aún no da nombre y correo</span>'}<span>Escribió por primera vez ${fmtDate(r.created_at, true)}</span></div>
        ${(r.messages || []).map((m) => `<div class="quote">${esc(m.text)}</div>`).join("")}
      </div><div class="row-actions">${actionButtons(r)}</div></li>`;
    ul.innerHTML = pend.map(item).join("") + (den.length ? `<li class="faint small" style="border-top:0;padding-top:20px">Rechazados (${den.length})</li>` + den.map(item).join("") : "");
    if (!pend.length && den.length) ul.insertAdjacentHTML("afterbegin", '<li class="empty">No hay solicitudes pendientes.</li>');
    bindAccess(ul, loadInbox, "#ib-req-msg");
  }
  function renderFeedback() {
    const ul = $("#ib-fb");
    const rows = FB.filter((f) => FFILTER === "all" || (FFILTER === "open" ? ["nuevo", "en_curso"].includes(f.status) : f.status === FFILTER));
    if (!rows.length) { ul.innerHTML = '<li class="empty">Nada por aquí.</li>'; return; }
    ul.innerHTML = rows.map((f) => `<li data-fid="${f.id}"><div class="inbox-item">
        <div class="meta"><span class="tipo">${esc(TIPOS[f.tipo] || f.tipo)}</span>${f.rating ? `<span>${"★".repeat(f.rating)}${"☆".repeat(5 - f.rating)}</span>` : ""}
          <span>${fmtDate(f.created_at, true)}</span><span>· ${esc(f.user.name || "Sin nombre")}${f.user.phone ? " (+" + esc(f.user.phone.replace(/^\+/, "")) + ")" : ""}</span>
          ${f.contact_ok ? '<span class="st ok">Acepta que lo contacten</span>' : ""}</div>
        <div class="quote">${esc(f.message)}</div></div>
      <div class="fb-tools">
        <div class="field"><label class="sr-only" for="fs-${f.id}">Estado</label><select id="fs-${f.id}" data-k="status">
          ${["nuevo", "en_curso", "resuelto", "descartado"].map((s) => `<option value="${s}" ${s === f.status ? "selected" : ""}>${{ nuevo: "Nuevo", en_curso: "En curso", resuelto: "Resuelto", descartado: "Descartado" }[s]}</option>`).join("")}</select></div>
        <div class="field"><label class="sr-only" for="fn-${f.id}">Nota interna</label><textarea id="fn-${f.id}" data-k="note" placeholder="Nota interna (qué vas a hacer)">${esc(f.note)}</textarea></div>
        <span class="small fb-msg"></span></div></li>`).join("");
    $$("li[data-fid]", ul).forEach((li) => {
      const fid = li.dataset.fid;
      $$("[data-k]", li).forEach((el) => el.addEventListener("change", async () => {
        const body = { [el.dataset.k]: el.value };
        try { await api("PUT", "/feedback/" + fid, body); const f = FB.find((x) => String(x.id) === fid); f[el.dataset.k] = el.value; $(".fb-msg", li).innerHTML = okMsg("Guardado."); if (el.dataset.k === "status") setTimeout(renderFeedback, 600); }
        catch (e) { $(".fb-msg", li).innerHTML = box("error-box", e.message); }
      }));
    });
  }
  async function loadInbox() { showInbox(await api("GET", "/inbox")); }
  function showInbox(d, fromCache) {
    const typing = document.activeElement && document.activeElement.closest && document.activeElement.closest("#ib-fb");
    if (typing && fromCache === false) return;   // no borrar lo que estás escribiendo
    FB = d.feedback || [];
    renderRequests(d.requests || []);
    renderFeedback();
  }
  // ---------- Inbox: seguridad ----------
  let SEC = [], SFILTER = "open";
  const SEV = { critical: "Crítico", high: "Alto", medium: "Medio", low: "Bajo", info: "Info" };
  function renderSecurity(d) {
    if (d) {
      SEC = d.events || [];
      const c = d.counts || {}, box = $("#sec-status"), last = d.last_check || {};
      box.classList.remove("warn", "bad");
      if (c.urgent) { box.classList.add("bad"); $("#sec-title").textContent = `${c.urgent} alerta(s) importante(s) por revisar`; }
      else if (c.open) { box.classList.add("warn"); $("#sec-title").textContent = `${c.open} aviso(s) por revisar`; }
      else $("#sec-title").textContent = "Todo en orden";
      $("#sec-sub").textContent = last.at ? `Último chequeo automático: ${fmtDate(last.at, true)} (${last.trigger || ""})${last.ok ? " · sin problemas" : ""}` : "Todavía no corre el primer chequeo automático.";
    }
    const ul = $("#sec-list");
    const rows = SEC.filter((e) => SFILTER === "all" || (e.status === "nuevo" && e.severity !== "info"));
    if (!rows.length) { ul.innerHTML = `<li class="empty">${SFILTER === "all" ? "Sin eventos registrados." : "Nada por revisar. 👌"}</li>`; return; }
    ul.innerHTML = rows.map((e) => `<li data-eid="${e.id}" class="${e.status === "revisado" ? "sec-done" : ""}"><div class="inbox-item">
        <p class="strong">${esc(e.title)}</p>
        <div class="meta"><span class="st sev-${esc(e.severity)}">${SEV[e.severity] || esc(e.severity)}</span>
          <span>${fmtDate(e.last_seen, true)}</span>${e.count > 1 ? `<span>· ${num(e.count)} veces</span>` : ""}
          ${e.ip ? `<span>· IP ${esc(e.ip)}</span>` : ""}${e.path ? `<span>· ${esc(e.path)}</span>` : ""}</div>
        <div class="quote sec-detail">${esc(e.detail)}</div></div>
      <div class="row-actions">${e.status === "nuevo" ? `<button class="btn ghost sm" data-sec="revisado">Revisado</button>` : `<button class="btn ghost sm" data-sec="nuevo">Volver a abrir</button>`}</div></li>`).join("");
    $$("button[data-sec]", ul).forEach((b) => b.addEventListener("click", async () => {
      const li = b.closest("li"); b.disabled = true;
      try { await api("PUT", "/seguridad/" + li.dataset.eid, { status: b.dataset.sec }); await loadSecurity(); }
      catch (err) { $("#sec-msg").innerHTML = box("error-box", err.message); b.disabled = false; }
    }));
  }
  async function loadSecurity() { renderSecurity(await api("GET", "/seguridad")); }
  function initSecurity() {
    if (!$("#sec-list")) return;
    $$("#sec-filter .chip").forEach((ch) => ch.addEventListener("click", () => {
      $$("#sec-filter .chip").forEach((x) => x.setAttribute("aria-pressed", "false")); ch.setAttribute("aria-pressed", "true");
      SFILTER = ch.dataset.f; renderSecurity();
    }));
    $("#sec-all").addEventListener("click", async () => {
      try { await api("POST", "/seguridad/revisar-todo"); await loadSecurity(); $("#sec-msg").innerHTML = okMsg("Todo marcado como revisado."); }
      catch (e) { $("#sec-msg").innerHTML = box("error-box", e.message); }
    });
    $("#sec-check").addEventListener("click", async (ev) => {
      const b = ev.currentTarget; b.disabled = true; b.textContent = "Revisando…";
      try {
        const r = await api("POST", "/seguridad/chequear");
        await loadSecurity();
        $("#sec-msg").innerHTML = okMsg(r.ok ? "Chequeo terminado: sin problemas." : "Chequeo terminado: revisa los avisos nuevos.");
      } catch (e) { $("#sec-msg").innerHTML = box("error-box", e.message); }
      b.disabled = false; b.textContent = "Ejecutar chequeo ahora";
    });
    live("/seguridad", (d) => renderSecurity(d), (e) => { $("#sec-list").innerHTML = `<li>${box("error-box", e.message)}</li>`; });
  }

  function pageInbox() {
    initSecurity();
    $$("#fb-filter .chip").forEach((ch) => ch.addEventListener("click", () => {
      $$("#fb-filter .chip").forEach((x) => x.setAttribute("aria-pressed", "false")); ch.setAttribute("aria-pressed", "true");
      FFILTER = ch.dataset.f; renderFeedback();
    }));
    live("/inbox", showInbox, (e) => { $("#ib-req").innerHTML = `<li>${box("error-box", e.message)}</li>`; });
  }

  // ---------- Fuentes ----------
  function renderSources(list) {
    const g = $("#src-grid");
    g.innerHTML = list.map((s) => `<article class="card glass src-card" data-sid="${esc(s.id)}">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div><p class="kind">${esc(s.kind)}</p><h3>${esc(s.name)}</h3></div>
        ${s.configured ? (s.needs_key ? '<span class="st ok">Configurada</span>' : '<span class="st ok">Sin clave</span>') : '<span class="st wait">Falta clave</span>'}</div>
      <dl><div><dt>Qué entrega</dt><dd>${esc(s.gives)}</dd></div><div><dt>Para qué la usa Finmate</dt><dd>${esc(s.used_for)}</dd></div>
        <div><dt>Plan y límites</dt><dd>${esc(s.plan)}${s.env ? ` · <code>${esc(s.env)}</code>` : ""}</dd></div></dl>
      <div class="field"><label class="sr-only" for="sn-${esc(s.id)}">Notas</label><textarea id="sn-${esc(s.id)}" placeholder="Notas o ideas sobre esta fuente">${esc(s.note)}</textarea></div>
      <p class="test faint"></p>
      <div class="foot"><button class="btn ghost sm" type="button" data-test>Probar</button>${s.url ? `<a class="small" href="${esc(s.url)}" target="_blank" rel="noopener">Documentación ↗</a>` : ""}</div>
    </article>`).join("");
    $$(".src-card", g).forEach((card) => {
      const sid = card.dataset.sid;
      $("[data-test]", card).addEventListener("click", () => testSource(card));
      $("textarea", card).addEventListener("change", async (e) => {
        try { await api("PUT", `/fuentes/${sid}/nota`, { note: e.target.value }); $(".test", card).innerHTML = okMsg("Nota guardada."); }
        catch (err) { $(".test", card).innerHTML = box("error-box", err.message); }
      });
    });
  }
  async function testSource(card) {
    const t = $(".test", card), b = $("[data-test]", card);
    b.disabled = true; t.className = "test faint"; t.textContent = "Probando…";
    try {
      const r = await api("POST", `/fuentes/${card.dataset.sid}/probar`);
      t.className = "test " + (r.ok ? "up" : "down");
      t.textContent = (r.ok ? "✓ Funciona" : "✗ Falló") + (r.detail ? " — " + r.detail : "") + (r.ms != null ? ` (${r.ms} ms)` : "");
    } catch (e) { t.className = "test down"; t.textContent = e.message; }
    b.disabled = false;
  }
  function renderAccess(d) {
    const cls = { completo: "ok", mixto: "warn", titular: "muted" };
    const words = { abierto: "abierto", pago: "de pago", bloqueado: "bloqueado", "poco texto": "poco texto" };
    $("#na-table tbody").innerHTML = (d.rows || []).map((r) => `<tr>
      <td data-label="Medio"><strong>${esc(r.name)}</strong></td>
      <td data-label="Acceso"><span class="st ${cls[r.access] || "muted"}">${esc(r.label)}</span>${r.changed ? ' <span class="small down">cambió</span>' : ""}</td>
      <td data-label="Cómo llega">${esc(r.via)}</td>
      <td data-label="Qué significa">${esc(r.note)}${r.articles && r.articles.length ? `<br><span class="faint small">Últimos artículos: ${r.articles.map((a) => esc(words[a] || a)).join(", ")}</span>` : ""}</td>
    </tr>`).join("");
    $("#na-when").textContent = d.checked_at ? "Última comprobación en vivo: " + new Date(d.checked_at).toLocaleString("es-CL") : "Aún sin comprobación en vivo (se muestra lo revisado el 26 nov 2026).";
  }
  function pageFuentes() {
    live("/acceso-medios", renderAccess, (e) => { $("#na-table tbody").innerHTML = `<tr><td colspan="4">${box("error-box", e.message)}</td></tr>`; });
    $("#na-check").addEventListener("click", async () => {
      const b = $("#na-check"); b.disabled = true; $("#na-when").textContent = "Comprobando los últimos artículos de cada medio…";
      try { renderAccess(await api("POST", "/acceso-medios/chequear")); } catch (e) { $("#na-when").textContent = e.message; }
      b.disabled = false;
    });
    live("/fuentes", (d, fromCache) => {
      const a = document.activeElement;
      if (fromCache === false && a && (a.closest("#src-grid") || a.id === "src-ideas")) return;   // estás escribiendo
      renderSources(d.sources || []); $("#src-ideas").value = d.ideas || "";
    }, (e) => { $("#src-grid").innerHTML = box("error-box", e.message); });
    $("#src-test-all").addEventListener("click", async () => { for (const c of $$(".src-card")) await testSource(c); });
    const imp = $("#cmf-import-btn");
    if (imp) imp.addEventListener("click", async () => {
      const files = $("#cmf-files").files;
      if (!files.length) { $("#cmf-import-msg").innerHTML = box("error-box", "Elige uno o más archivos .xls."); return; }
      const fd = new FormData(); for (const f of files) fd.append("files", f);
      imp.disabled = true; $("#cmf-import-msg").innerHTML = '<p class="faint">Importando…</p>';
      try {
        const r = await fetch("/admin/api/fondos/importar", { method: "POST", body: fd, headers: { "X-Finmate": "1" }, credentials: "same-origin" });
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || ("Error " + r.status));
        $("#cmf-import-msg").innerHTML = "<ul>" + d.results.map((x) => "<li>" + esc(x.file) + ": " + (x.error ? '<span class="down">' + esc(x.error) + "</span>" : esc(x.date) + " · " + esc(x.series) + " series") + "</li>").join("") + "</ul>" +
          '<p class="faint small">Ahora hay ' + esc(d.status.dates) + " fechas guardadas.</p>";
        $("#cmf-files").value = "";
      } catch (e) { $("#cmf-import-msg").innerHTML = box("error-box", e.message); }
      imp.disabled = false;
    });
    $("#src-ideas-save").addEventListener("click", async () => {
      try { await api("PUT", "/fuentes/_ideas/nota", { note: $("#src-ideas").value }); $("#src-ideas-msg").innerHTML = okMsg("Ideas guardadas."); }
      catch (e) { $("#src-ideas-msg").innerHTML = box("error-box", e.message); }
    });
  }

  // ---------- Anuncios ----------
  const AN_EXAMPLE = {
    title: "Ahora tus noticias se adaptan a ti",
    body: "Desde hoy, cada noticia que te mande trae botones 1, 2 y 3 para que me digas qué tan relevante fue (3 = muy relevante).\n\n" +
      "*Qué pasa con cada nivel*\n" +
      "• 3: te llega por el chat durante el día\n" +
      "• 2: va en tus resúmenes de inicio y cierre de jornada\n" +
      "• 1: solo si me preguntas por el tema\n\n" +
      "No es blanco o negro: si algo te parece 1, no desaparece de inmediato. Te lo voy mostrando cada vez menos, hasta que tus notas confirmen que no te interesa.\n\n" +
      "Puedes ver y cambiar lo que aprendí en tu app, en Ajustes → Tus noticias.",
  };
  // Formato de WhatsApp: *negrita*, _cursiva_, ~tachado~
  function waFormat(text) {
    return esc(text)
      .replace(/(^|[\s(])\*([^*\n]+)\*(?=[\s).,!?:;]|$)/g, "$1<strong>$2</strong>")
      .replace(/(^|[\s(])_([^_\n]+)_(?=[\s).,!?:;]|$)/g, "$1<em>$2</em>")
      .replace(/(^|[\s(])~([^~\n]+)~(?=[\s).,!?:;]|$)/g, "$1<s>$2</s>");
  }
  const AN_ST = { sent: ["ok", "Llegó"], later: ["ok", "Llegó después"], template: ["wait", "Aviso por plantilla"],
                  pending: ["wait", "Espera que escriba"], failed: ["no", "No llegó"] };
  function pageAnuncios() {
    const DKEY = "fm-admin-anuncio-borrador";
    let aud = "test", confirmAll = false, reach = { total: 0, now: 0, later: 0 }, testReach = { total: 0 };
    const title = $("#an-title"), body = $("#an-body");
    function message() {
      const t = title.value.trim().replace(/\*/g, ""), b = body.value.trim();
      return b ? (t ? "📣 *" + t + "*\n\n" + b : "📣 " + b) : "";
    }
    function paint() {
      const m = message();
      $("#an-preview").innerHTML = m ? waFormat(m) : '<span class="faint">Tu anuncio aparecerá aquí.</span>';
      $("#an-count").textContent = body.value.length + " / 3000";
      try { localStorage.setItem(DKEY, JSON.stringify({ t: title.value, b: body.value })); } catch (e) {}
    }
    function paintReach() {
      $$("#an-aud .chip").forEach((c) => c.setAttribute("aria-pressed", String(c.dataset.aud === aud)));
      $("#an-reach").textContent = aud === "test"
        ? `Te llega a ti (${testReach.total} ${testReach.total === 1 ? "número de admin" : "números de admin"}), para revisar cómo se ve.`
        : `${reach.total} usuarios con acceso: ${reach.now} lo reciben ahora y ${reach.later} cuando vuelvan a escribir (WhatsApp no deja escribirles antes).`;
      resetConfirm();
    }
    function resetConfirm() {
      confirmAll = false;
      $("#an-send").textContent = aud === "test" ? "Enviar prueba" : `Enviar a ${reach.total} usuarios`;
      $("#an-send").disabled = aud === "all" && !reach.total;
      $("#an-cancel").hidden = true;
    }
    function renderHistory(list) {
      $("#an-list").innerHTML = list.map((a) => {
        const c = a.counts, stats = Object.keys(AN_ST).filter((k) => c[k]).map((k) =>
          `<span class="st ${AN_ST[k][0]}">${AN_ST[k][1]}: ${c[k]}</span>`).join("");
        return `<li class="ann-item" style="display:block"><div style="display:flex;flex-wrap:wrap;gap:10px;justify-content:space-between;align-items:flex-start">
          <div><p class="strong">${esc(a.title || a.body.slice(0, 60) + (a.body.length > 60 ? "…" : ""))}</p>
            <p class="faint small">${fmtDate(a.created_at, true)} · ${a.audience === "test" ? "Prueba" : "Todos los usuarios"} · ${a.delivered} de ${a.total} ya lo tienen</p></div>
          <div class="row-actions"><button class="btn ghost sm" type="button" data-an-toggle>Ver texto</button>
            ${c.pending ? `<button class="btn ghost sm" type="button" data-an-stop="${a.id}">Dejar de entregar</button>` : ""}</div></div>
          <div class="ann-stats">${stats}</div><div class="ann-text" hidden>${waFormat(a.text)}</div></li>`;
      }).join("") || '<li class="empty">Todavía no mandas anuncios.</li>';
      $$("[data-an-toggle]").forEach((b) => b.addEventListener("click", () => {
        const t = $(".ann-text", b.closest("li")); t.hidden = !t.hidden; b.textContent = t.hidden ? "Ver texto" : "Ocultar";
      }));
      $$("[data-an-stop]").forEach((b) => b.addEventListener("click", async () => {
        try { const r = await api("POST", `/anuncios/${b.dataset.anStop}/cancelar`); renderHistory(r.history); }
        catch (e) { $("#an-msg").innerHTML = box("error-box", e.message); }
      }));
    }
    function apply(d) {
      reach = d.reach || reach; testReach = d.test_reach || testReach;
      renderHistory(d.history || []); paintReach();
    }
    try { const dr = JSON.parse(localStorage.getItem(DKEY) || "null"); if (dr) { title.value = dr.t || ""; body.value = dr.b || ""; } } catch (e) {}
    paint();
    [title, body].forEach((el) => el.addEventListener("input", () => { paint(); resetConfirm(); }));
    $("#an-example").addEventListener("click", () => {
      if (body.value.trim() && body.value.trim() !== AN_EXAMPLE.body && !confirmReplace()) return;
      title.value = AN_EXAMPLE.title; body.value = AN_EXAMPLE.body; paint();
    });
    let replaceArmed = false;
    function confirmReplace() {
      if (replaceArmed) { replaceArmed = false; return true; }
      replaceArmed = true; $("#an-msg").innerHTML = '<span class="faint small">Ya tienes un texto. Toca "Usar ejemplo" otra vez para reemplazarlo.</span>';
      setTimeout(() => { replaceArmed = false; }, 5000); return false;
    }
    $$("#an-aud .chip").forEach((c) => c.addEventListener("click", () => { aud = c.dataset.aud; paintReach(); }));
    $("#an-ai").addEventListener("click", async () => {
      const b = $("#an-ai"); b.disabled = true; const old = b.textContent; b.textContent = "Redactando…";
      try {
        const notes = (title.value.trim() ? title.value.trim() + "\n" : "") + body.value;
        const r = await api("POST", "/anuncios/redactar", { notes: notes });
        if (r.title) title.value = r.title; body.value = r.body; paint(); resetConfirm();
        $("#an-msg").innerHTML = okMsg("Listo. Revísalo y ajústalo antes de enviar.");
      } catch (e) { $("#an-msg").innerHTML = box("error-box", e.message); }
      b.disabled = false; b.textContent = old;
    });
    $("#an-cancel").addEventListener("click", resetConfirm);
    $("#an-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      if (body.value.trim().length < 5) { $("#an-msg").innerHTML = box("error-box", "Escribe el mensaje del anuncio."); return; }
      if (aud === "all" && !confirmAll) {      // segundo toque para confirmar: no se puede deshacer
        confirmAll = true; $("#an-send").textContent = `Sí, enviar a ${reach.total} usuarios`; $("#an-cancel").hidden = false;
        $("#an-msg").innerHTML = '<span class="faint small">Un anuncio enviado no se puede borrar de WhatsApp. ¿Confirmas?</span>'; return;
      }
      const btn = $("#an-send"); btn.disabled = true;
      try {
        const r = await api("POST", "/anuncios", { title: title.value, body: body.value, audience: aud });
        apply(r);
        const c = r.announcement.counts;
        if (aud === "all") {
          title.value = ""; body.value = ""; paint();
          $("#an-msg").innerHTML = okMsg(`Enviado: ${c.sent} lo recibieron ahora, ${c.pending + c.template} cuando vuelvan a escribir${c.failed ? `, ${c.failed} fallaron` : ""}.`);
        } else {
          $("#an-msg").innerHTML = c.failed ? box("error-box", "La prueba no llegó. Revisa la configuración de WhatsApp.") : okMsg("Prueba enviada. Revisa tu WhatsApp.");
        }
      } catch (err) { $("#an-msg").innerHTML = box("error-box", err.message); }
      btn.disabled = false; resetConfirm();
    });
    live("/anuncios", apply, (e) => { $("#an-list").innerHTML = `<li>${box("error-box", e.message)}</li>`; });
  }

  // Barra fina arriba mientras abre la otra pestaña (así se nota que está cargando)
  function showProgress() {
    let bar = $(".nav-progress");
    if (!bar) { bar = document.createElement("div"); bar.className = "nav-progress"; document.body.appendChild(bar); }
    requestAnimationFrame(() => bar.classList.add("go"));
  }

  // ---------- celular: igual que la app de usuarios ----------
  // Barra de pestañas abajo con la "píldora" azul, se esconde al bajar,
  // deslizar con el dedo cambia de pestaña y no se puede hacer zoom.
  const mq = window.matchMedia("(max-width: 760px)");
  // Celular: las 5 pestañas están en la misma página, lado a lado (base.html).
  // Al arrastrar, el riel sigue al dedo y la vecina ya se ve; al soltar termina
  // de deslizarse sin recargar (igual que el panel de usuarios). La URL se
  // actualiza con history.pushState. En computador los enlaces navegan normal.
  function initTabs(modules) {
    const rail = $(".rail"); const track = document.getElementById("track"); const main = document.getElementById("main");
    if (!rail || !track || !main) return;
    const links = $$("a", rail);
    const panes = $$(".pane", track);
    const names = panes.map((p) => p.dataset.pane);
    const pill = $(".tab-pill", rail);
    const calm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const EASE = "cubic-bezier(.22,.8,.24,1)";
    let idx = names.indexOf((document.body.dataset.page || "").replace(/^admin-/, ""));
    if (idx < 0) return;
    let moveToken = 0;
    let sx = 0, sy = 0, lastX = 0, lastT = 0, vx = 0, dx = 0, lock = null, on = false;
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
      if (!pill) return;
      const cur = links[idx]; const n = links[idx + (frac > 0 ? 1 : -1)];
      let left = cur.offsetLeft, w = cur.offsetWidth;
      if (n && frac) { const f = Math.min(Math.abs(frac), 1); left += (n.offsetLeft - cur.offsetLeft) * f; w += (n.offsetWidth - cur.offsetWidth) * f; }
      pill.style.transition = ms === 0 ? "none" : "";
      pill.style.transform = "translateX(" + left + "px)"; pill.style.width = w + "px";
      const near = n && Math.abs(frac) > 0.5 ? n : cur;
      links.forEach((a) => a.classList.toggle("lit", a === near));
    }
    function alignNeighbors(onDrag) {
      const y = onDrag ? window.scrollY : 0;
      panes.forEach((p, i) => { p.style.transform = y && i !== idx ? "translateY(" + y + "px)" : ""; });
    }
    function markActive() {
      panes.forEach((p, i) => {
        const act = i === idx;
        p.classList.toggle("active", act);
        if (act) { p.removeAttribute("aria-hidden"); p.inert = false; } else { p.setAttribute("aria-hidden", "true"); p.inert = true; }
      });
      links.forEach((a, i) => { if (i === idx) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
      document.body.dataset.page = "admin-" + names[idx];
      document.title = "Finmate Admin — " + (panes[idx].dataset.title || links[idx].getAttribute("title") || "");
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
      const token = ++moveToken;
      const finish = () => {
        if (token !== moveToken) return;
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
      setTimeout(() => { startPane(idx - 1); startPane(idx + 1); }, ms + 150);
    }
    function layout() {
      if (mq.matches) { setTrack(-idx * width(), 0); placePill(0, 0); }
      else { track.style.transform = ""; track.style.transition = ""; }
    }
    markActive(); layout();
    window.addEventListener("resize", layout);
    // Al volver a la app se deja todo en su lugar (por si quedó un gesto a medias)
    document.addEventListener("visibilitychange", () => {
      on = false; lock = null; dx = 0; moveToken++;
      rail.classList.remove("dragging");
      alignNeighbors(false); markActive(); layout();
      track.style.transition = "none";
    });
    mq.addEventListener ? mq.addEventListener("change", layout) : mq.addListener(layout);
    window.addEventListener("popstate", () => {
      const i = links.findIndex((a) => a.href === location.href || a.pathname === location.pathname);
      if (i >= 0 && mq.matches) goTo(i, { push: false }); else if (i >= 0) location.reload();
    });
    setTimeout(() => { if (mq.matches) { startPane(idx - 1); startPane(idx + 1); } }, 600);

    links.forEach((a, i) => a.addEventListener("click", (e) => {
      if (e.metaKey || e.ctrlKey) return;
      e.preventDefault();
      if (!mq.matches) { if (i !== idx) { showProgress(); location.href = a.href; } return; }
      goTo(i, { ms: Math.min(260 + 60 * Math.abs(i - idx), 420) });
    }));

    function scrollsX(el) {
      for (; el && el !== main; el = el.parentElement) {
        const ox = getComputedStyle(el).overflowX;
        if ((ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 2) return true;
      }
      return false;
    }
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
      vx = 0.8 * ((x - lastX) / Math.max(now - lastT, 1)) + 0.2 * vx;
      lastX = x; lastT = now;
      const atEdge = (mx > 0 && idx === 0) || (mx < 0 && idx === panes.length - 1);
      dx = atEdge ? mx / 3 : mx;
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
      const remaining = Math.abs(-target * w - (-idx * w + dx));
      const ms = Math.round(Math.max(160, Math.min(340, flick ? remaining / Math.abs(vx) : remaining * 0.9)));
      if (target !== idx) goTo(target, { ms: ms });
      else { setTrack(-idx * w, ms); placePill(0); setTimeout(() => alignNeighbors(false), ms + 20); }
    }
    main.addEventListener("touchend", end);
    main.addEventListener("touchcancel", end);
  }

  // Celular: la barra de abajo se esconde al bajar y vuelve al subir
  function initAutoHideRail() {
    const rail = $(".rail"); if (!rail) return;
    let lastY = window.scrollY, acc = 0, ticking = false;
    function update() {
      ticking = false;
      const y = Math.max(window.scrollY, 0), dy = y - lastY; lastY = y;
      if (!mq.matches) { rail.classList.remove("rail-hidden"); return; }
      const nearBottom = window.innerHeight + y >= document.documentElement.scrollHeight - 40;
      if (y < 60 || nearBottom) { acc = 0; rail.classList.remove("rail-hidden"); return; }
      acc = (acc > 0) === (dy > 0) ? acc + dy : dy;
      if (acc > 24) rail.classList.add("rail-hidden"); else if (acc < -12) rail.classList.remove("rail-hidden");
    }
    window.addEventListener("scroll", () => { if (!ticking) { ticking = true; requestAnimationFrame(update); } }, { passive: true });
    document.addEventListener("finmate:pane", () => { acc = 0; lastY = window.scrollY; rail.classList.remove("rail-hidden"); });
  }
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

  // Al volver con "atrás" el navegador muestra la página guardada en memoria
  // (con la pestaña equivocada marcada y datos viejos): se recarga. Lo mismo si
  // la app estuvo más de 10 minutos en segundo plano.
  function freshOnReturn() {
    window.addEventListener("pageshow", (e) => { if (e.persisted) location.reload(); });
    let hiddenAt = 0;
    document.addEventListener("visibilitychange", () => {
      if (document.hidden) { hiddenAt = Date.now(); return; }
      if (hiddenAt && Date.now() - hiddenAt > 10 * 60 * 1000) location.reload();
    });
  }

  preventZoom();
  freshOnReturn();
  if (page === "admin-login") pageLogin();
  else {
    const MODULES = {
      costos: () => { live("/resumen", renderCostos); pageCostos(); },
      usuarios: pageUsuarios, inbox: pageInbox, anuncios: pageAnuncios, fuentes: pageFuentes,
    };
    initCommon();
    const cur = page.replace(/^admin-/, "");
    try { (MODULES[cur] || function () {})(); } catch (e) {}
    initTabs(MODULES);
    initAutoHideRail();
  }
})();
