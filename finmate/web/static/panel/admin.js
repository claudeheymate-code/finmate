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
    return data;
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
    if (out) out.addEventListener("click", async () => { try { await api("POST", "/logout"); } catch (e) {} location.href = "/admin/login"; });
    const badge = $("#inbox-badge");
    if (badge) api("GET", "/resumen").then((d) => {
      const n = ((d.users || {}).pending || 0) + (d.feedback_new || 0) + ((d.security || {}).open || 0);
      if (n > 0) { badge.textContent = n > 99 ? "99+" : n; badge.hidden = false; }
      if (page === "admin-costos") renderCostos(d);
    }).catch(() => {});
  }

  // ---------- Login ----------
  function pageLogin() {
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
      <td class="nowrap" data-label="Último mensaje" title="${esc(fmtDate(u.last_message_at, true))}">${ago(u.last_message_at)}</td>
      <td class="r" data-label="Mensajes">${num(u.messages)}</td><td class="r hide-sm">${num(u.watchlist)}</td><td class="r hide-sm">${num(u.portfolio)}</td>
      <td data-label="Acceso">${stPill(u.status)}</td>
      <td><div class="row-actions">${actionButtons(u)}</div></td></tr>`).join("")
      : '<tr><td colspan="9" class="empty">No hay usuarios con ese filtro.</td></tr>';
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
  async function loadUsers() {
    const d = await api("GET", "/usuarios");
    USERS = d.users || [];
    const c = d.counts || {};
    $("#us-approved").textContent = num(c.approved); $("#us-active").textContent = num(c.active_7d);
    $("#us-pending").textContent = num(c.pending); $("#us-msgs").textContent = num(c.messages);
    renderUsers();
  }
  function pageUsuarios() {
    $("#us-q").addEventListener("input", renderUsers);
    $$("#us-filter .chip").forEach((ch) => ch.addEventListener("click", () => {
      $$("#us-filter .chip").forEach((x) => x.setAttribute("aria-pressed", "false")); ch.setAttribute("aria-pressed", "true");
      UFILTER = ch.dataset.f; renderUsers();
    }));
    loadUsers().catch((e) => { $("#us-rows").innerHTML = `<tr><td colspan="9">${box("error-box", e.message)}</td></tr>`; });
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
  async function loadInbox() {
    const d = await api("GET", "/inbox");
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
    loadSecurity().catch((e) => { $("#sec-list").innerHTML = `<li>${box("error-box", e.message)}</li>`; });
  }

  function pageInbox() {
    initSecurity();
    $$("#fb-filter .chip").forEach((ch) => ch.addEventListener("click", () => {
      $$("#fb-filter .chip").forEach((x) => x.setAttribute("aria-pressed", "false")); ch.setAttribute("aria-pressed", "true");
      FFILTER = ch.dataset.f; renderFeedback();
    }));
    loadInbox().catch((e) => { $("#ib-req").innerHTML = `<li>${box("error-box", e.message)}</li>`; });
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
  function pageFuentes() {
    api("GET", "/fuentes").then((d) => { renderSources(d.sources || []); $("#src-ideas").value = d.ideas || ""; })
      .catch((e) => { $("#src-grid").innerHTML = box("error-box", e.message); });
    $("#src-test-all").addEventListener("click", async () => { for (const c of $$(".src-card")) await testSource(c); });
    $("#src-ideas-save").addEventListener("click", async () => {
      try { await api("PUT", "/fuentes/_ideas/nota", { note: $("#src-ideas").value }); $("#src-ideas-msg").innerHTML = okMsg("Ideas guardadas."); }
      catch (e) { $("#src-ideas-msg").innerHTML = box("error-box", e.message); }
    });
  }

  // ---------- celular: igual que la app de usuarios ----------
  // Barra de pestañas abajo con la "píldora" azul, se esconde al bajar,
  // deslizar con el dedo cambia de pestaña y no se puede hacer zoom.
  const mq = window.matchMedia("(max-width: 760px)");
  function initRail() {
    const rail = $(".rail"); if (!rail) return;
    const pill = $(".tab-pill", rail);
    const links = $$("a", rail);
    const place = (a) => { if (!pill || !a) return; pill.style.width = a.offsetWidth + "px"; pill.style.transform = `translateX(${a.offsetLeft}px)`; };
    const current = () => links.find((a) => a.getAttribute("aria-current") === "page");
    if (pill) { pill.style.transition = "none"; place(current()); requestAnimationFrame(() => { pill.style.transition = ""; }); }
    window.addEventListener("resize", () => place(current()));
    const go = (a) => {
      if (!a || a === current()) return;
      if (mq.matches && pill) {
        links.forEach((x) => x.removeAttribute("aria-current")); a.setAttribute("aria-current", "page"); place(a);
        setTimeout(() => { location.href = a.href; }, 200);
      } else location.href = a.href;
    };
    links.forEach((a) => a.addEventListener("click", (e) => { if (e.metaKey || e.ctrlKey) return; e.preventDefault(); go(a); }));
    // Deslizar entre pestañas (no dentro de tablas que se desplazan ni campos)
    let x0 = null, y0 = 0;
    document.addEventListener("touchstart", (e) => {
      if (!mq.matches || e.touches.length !== 1 || e.target.closest(".table-wrap, input, textarea, select, .rail")) { x0 = null; return; }
      x0 = e.touches[0].clientX; y0 = e.touches[0].clientY;
    }, { passive: true });
    document.addEventListener("touchend", (e) => {
      if (x0 === null) return;
      const dx = e.changedTouches[0].clientX - x0, dy = e.changedTouches[0].clientY - y0; x0 = null;
      if (Math.abs(dx) < 70 || Math.abs(dx) < Math.abs(dy) * 2) return;
      const i = links.indexOf(current());
      go(links[i + (dx < 0 ? 1 : -1)]);
    }, { passive: true });
    // Se esconde al bajar y vuelve al subir
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
    initRail();
    initCommon();
    if (page === "admin-costos") pageCostos();
    if (page === "admin-usuarios") pageUsuarios();
    if (page === "admin-inbox") pageInbox();
    if (page === "admin-fuentes") pageFuentes();
  }
})();
