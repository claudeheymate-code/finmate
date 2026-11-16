/* Finmate — versión de prueba del panel.
   Reemplaza al servidor: responde las mismas rutas /api/* que el backend real
   (finmate/web/api.py) con datos de ejemplo y guarda los cambios solo en este
   navegador. El resto del panel (HTML, CSS y panel.js) es el mismo código real. */
(function () {
  "use strict";
  var SEED = {"today": "2026-11-16", "feedbackTo": "claude.heymate@gmail.com", "prices": {"AAPL": [352.07, -1.18], "JPM": [301.15, 0.42], "MSFT": [468.2, 0.84], "TLT": [88.7, 0.31], "KO": [71.3, -0.25], "XOM": [104.6, -1.87], "TSLA": [402.8, 2.95], "BND": [73.1, 0.12], "NVDA": [186.64, 2.78], "AMZN": [231.4, -0.66], "GOOGL": [262.15, 0.92], "META": [698.3, 1.41], "NFLX": [1124.5, -0.38], "SPY": [668.2, 0.21], "QQQ": [598.75, 0.44], "VOO": [614.1, 0.2], "AGG": [99.4, 0.08], "IEF": [96.2, 0.1], "V": [351.9, 0.33], "WMT": [104.25, -0.12], "DIS": [112.6, 0.57], "AMD": [238.9, 3.12]}, "sectors": {"AMZN": "Consumo", "GOOGL": "Tecnología", "META": "Tecnología", "NFLX": "Comunicaciones", "SPY": "Índice amplio", "QQQ": "Índice amplio", "VOO": "Índice amplio", "AGG": "Bonos", "IEF": "Bonos", "V": "Financiero", "WMT": "Consumo", "DIS": "Comunicaciones", "AMD": "Tecnología", "NVDA": "Tecnología"}, "bondEtfs": ["TLT", "IEF", "SHY", "BND", "AGG", "LQD", "HYG", "JNK", "TIP", "BIL", "SGOV", "GOVT", "MUB", "EMB", "BNDX"], "broadEtfs": ["SPY", "VOO", "IVV", "VTI", "QQQ", "QQQM", "DIA", "IWM", "VT", "VXUS", "VEA", "VWO"], "categories": ["Evento Social", "Polola", "Copete", "Comidas", "Regalos", "Viajes", "Otros"], "catalogo": [{"code": "USD_CLP", "country": "CL", "freq": "diario", "name": "Dólar / Peso chileno", "relevance": "alta"}, {"code": "IPC_CL", "country": "CL", "freq": "mensual", "name": "IPC Chile", "relevance": "alta"}, {"code": "GDP_CL", "country": "CL", "freq": "mensual", "name": "PIB Chile (Imacec)", "relevance": "alta"}, {"code": "COPPER", "country": "CL", "freq": "diario", "name": "Precio del cobre", "relevance": "alta"}, {"code": "BCCh_RATE", "country": "CL", "freq": "~8 veces/año", "name": "Tasa Banco Central de Chile", "relevance": "alta"}, {"code": "UNEMPLOYMENT_CL", "country": "CL", "freq": "mensual", "name": "Desempleo Chile", "relevance": "media"}, {"code": "FED_RATE", "country": "US", "freq": "~8 veces/año", "name": "Decisión de tasa Fed", "relevance": "alta"}, {"code": "CPI_US", "country": "US", "freq": "mensual", "name": "Inflación EE.UU. (CPI)", "relevance": "alta"}, {"code": "PCE_US", "country": "US", "freq": "mensual", "name": "Inflación PCE EE.UU.", "relevance": "alta"}, {"code": "NFP", "country": "US", "freq": "mensual", "name": "Nóminas no agrícolas (NFP)", "relevance": "alta"}, {"code": "GDP_US", "country": "US", "freq": "trimestral", "name": "PIB EE.UU.", "relevance": "alta"}, {"code": "UNEMPLOYMENT_US", "country": "US", "freq": "mensual", "name": "Desempleo EE.UU.", "relevance": "media"}, {"code": "ISM_MFG", "country": "US", "freq": "mensual", "name": "ISM Manufacturero", "relevance": "media"}, {"code": "FOMC_MINUTES", "country": "US", "freq": "~8 veces/año", "name": "Minutas FOMC", "relevance": "media"}, {"code": "RETAIL_SALES_US", "country": "US", "freq": "mensual", "name": "Ventas minoristas EE.UU.", "relevance": "media"}], "state": {"logged": false, "positions": [{"symbol": "AAPL", "quantity": 10.0, "avg_cost": 150.0, "asset_class": "Renta variable", "sector": "Tecnología"}, {"symbol": "JPM", "quantity": 8.0, "avg_cost": 245.0, "asset_class": "Renta variable", "sector": "Financiero"}, {"symbol": "MSFT", "quantity": 5.0, "avg_cost": 410.5, "asset_class": "Renta variable", "sector": "Tecnología"}, {"symbol": "TLT", "quantity": 25.0, "avg_cost": 92.0, "asset_class": "Renta fija", "sector": "Bonos"}, {"symbol": "KO", "quantity": 20.0, "avg_cost": 68.0, "asset_class": "Renta variable", "sector": "Consumo"}, {"symbol": "XOM", "quantity": 12.0, "avg_cost": 118.0, "asset_class": "Renta variable", "sector": "Energía"}, {"symbol": "TSLA", "quantity": 3.0, "avg_cost": 420.0, "asset_class": "Renta variable", "sector": "Consumo"}, {"symbol": "BND", "quantity": 15.0, "avg_cost": 72.0, "asset_class": "Renta fija", "sector": "Bonos"}], "watchlist": [{"symbol": "NVDA", "note": null}], "txs": [{"amount": -120000.0, "category": "Viajes", "date": "2026-10-26", "description": "Pasajes", "has_receipt": false, "id": 16, "merchant": "", "occasion": "Viaje al sur", "receipt_url": "", "tipo": "gasto"}, {"amount": -15000.0, "category": "Regalos", "date": "2026-10-24", "description": "Regalo", "has_receipt": false, "id": 15, "merchant": "", "occasion": "Día del profesor", "receipt_url": "", "tipo": "gasto"}, {"amount": -61200.0, "category": "Comidas", "date": "2026-10-20", "description": "Supermercado", "has_receipt": false, "id": 14, "merchant": "", "occasion": "Compras del mes", "receipt_url": "", "tipo": "gasto"}, {"amount": -52000.0, "category": "Copete", "date": "2026-10-18", "description": "Carrete", "has_receipt": false, "id": 13, "merchant": "", "occasion": "Fiestas Patrias atrasadas", "receipt_url": "", "tipo": "gasto"}, {"amount": -48000.0, "category": "Polola", "date": "2026-10-11", "description": "Cena", "has_receipt": false, "id": 12, "merchant": "", "occasion": "Salida del viernes", "receipt_url": "", "tipo": "gasto"}, {"amount": -30000.0, "category": "Evento Social", "date": "2026-10-05", "description": "Matrimonio", "has_receipt": false, "id": 11, "merchant": "", "occasion": "Matrimonio de mi primo", "receipt_url": "", "tipo": "gasto"}, {"amount": -18900.0, "category": "Viajes", "date": "2026-11-15", "description": "Bus a Viña", "has_receipt": false, "id": 10, "merchant": "Turbus", "occasion": "Fin de semana en la costa", "receipt_url": "", "tipo": "gasto"}, {"amount": -15000.0, "category": "Copete", "date": "2026-11-14", "description": "Bar", "has_receipt": false, "id": 9, "merchant": "Bar La Junta", "occasion": "Viernes con amigos", "receipt_url": "", "tipo": "gasto"}, {"amount": -20000.0, "category": "Polola", "date": "2026-11-14", "description": "Cine", "has_receipt": false, "id": 8, "merchant": "Cinemark", "occasion": "Salida del sábado", "receipt_url": "", "tipo": "gasto"}, {"amount": -28000.0, "category": "Comidas", "date": "2026-11-12", "description": "Supermercado", "has_receipt": false, "id": 7, "merchant": "Supermercado Líder", "occasion": "Compra de la semana", "receipt_url": "", "tipo": "gasto"}, {"amount": -18300.0, "category": "Comidas", "date": "2026-11-10", "description": "Sushi", "has_receipt": false, "id": 6, "merchant": "Sushi Express", "occasion": "Pedido del domingo", "receipt_url": "", "tipo": "gasto"}, {"amount": -42000.0, "category": "Polola", "date": "2026-11-09", "description": "Cena aniversario", "has_receipt": false, "id": 5, "merchant": "Restaurante Liguria", "occasion": "Aniversario de 1 año", "receipt_url": "", "tipo": "gasto"}, {"amount": -8000.0, "category": "Comidas", "date": "2026-11-08", "description": "Almuerzo", "has_receipt": false, "id": 4, "merchant": "Café Altura", "occasion": "Almuerzo de trabajo", "receipt_url": "", "tipo": "gasto"}, {"amount": -23500.0, "category": "Copete", "date": "2026-11-07", "description": "Previa", "has_receipt": false, "id": 3, "merchant": "Botillería El Sol", "occasion": "Previa en lo de Nico", "receipt_url": "", "tipo": "gasto"}, {"amount": 500000.0, "category": "Otros", "date": "2026-11-01", "description": "Sueldo", "has_receipt": false, "id": 17, "merchant": "", "occasion": "", "receipt_url": "", "tipo": "ingreso"}, {"amount": -25000.0, "category": "Regalos", "date": "2026-11-01", "description": "Regalo", "has_receipt": false, "id": 2, "merchant": "Falabella", "occasion": "Cumpleaños de la Cata", "receipt_url": "", "tipo": "gasto"}, {"amount": -45000.0, "category": "Evento Social", "date": "2026-11-01", "description": "Bowling", "has_receipt": false, "id": 1, "merchant": "Bowling Center", "occasion": "Cumpleaños de la Cata", "receipt_url": "", "tipo": "gasto"}], "nextId": 18, "personalidad": {"frecuencia_chistes": 3, "humor": 8, "nivel_conversador": 5, "sarcasmo": 3, "tono": "casual"}, "temas": [{"tipo": "sector", "valor": "bancos regionales"}], "indicadores": ["CPI_US"], "avisos": {"watchlist_threshold_pct": 5.0, "weekly_summary_enabled": true}, "phone": "+56900000000"}};
  var KEY = "finmate-demo-v1";
  var mem = null;
  function load() {
    try { var raw = localStorage.getItem(KEY); if (raw) return JSON.parse(raw); } catch (e) {}
    return mem || JSON.parse(JSON.stringify(SEED.state));
  }
  function save(s) { mem = s; try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) {} }
  var S = load();

  document.addEventListener("click", function (e) {
    if (e.target && e.target.id === "demo-reset") {
      try { localStorage.removeItem(KEY); } catch (err) {}
      mem = null; location.href = "acceso.html";
    }
  });

  var CATS = SEED.categories;
  var TONOS = ["profesional", "casual", "amigo"];
  var PINT = ["humor", "sarcasmo", "frecuencia_chistes", "nivel_conversador"];
  var NEWS_TIPOS = ["ticker", "sector", "pais", "keyword"];
  var SYM_RE = /^[A-Z][A-Z0-9.\-]{0,9}$/;

  function json(status, obj) {
    return new Response(JSON.stringify(obj), { status: status, headers: { "Content-Type": "application/json" } });
  }
  function err(msg, status) { return json(status || 400, { error: msg }); }
  function num(v) { if (v === null || v === undefined || v === "") return null; var n = parseFloat(String(v).replace(",", ".")); return isNaN(n) ? null : n; }
  function sym(v) { var s = String(v || "").trim().toUpperCase(); return SYM_RE.test(s) ? s : ""; }
  function quote(s) { var p = SEED.prices[s]; return p ? { price: p[0], change_pct: p[1], is_closed: false } : null; }
  function classify(s) {
    if (SEED.bondEtfs.indexOf(s) >= 0) return ["Renta fija", "Bonos"];
    if (SEED.broadEtfs.indexOf(s) >= 0) return ["Renta variable", "Índice amplio"];
    return ["Renta variable", SEED.sectors[s] || "Otros"];
  }
  function maskPhone(p) { return p.length > 9 ? p.slice(0, 5) + " •••• " + p.slice(-4) : p; }

  // ── Portafolio (misma lógica que finmate/services/portfolio.py) ──
  function group(ps, key) {
    var t = {}; ps.forEach(function (p) { if (p.value !== null) t[p[key]] = (t[p[key]] || 0) + p.value; });
    var grand = Object.keys(t).reduce(function (a, k) { return a + t[k]; }, 0);
    return Object.keys(t).sort(function (a, b) { return t[b] - t[a]; })
      .map(function (k) { return { name: k, value: t[k], pct: grand ? t[k] / grand * 100 : 0 }; });
  }
  function portfolio() {
    var missing = [];
    var ps = S.positions.map(function (h) {
      var q = quote(h.symbol);
      var price = q ? q.price : null;
      var value = price !== null ? price * h.quantity : null;
      var cost = h.avg_cost ? h.avg_cost * h.quantity : null;
      var pnl = value !== null && cost !== null ? value - cost : null;
      if (price === null) missing.push(h.symbol);
      return { symbol: h.symbol, quantity: h.quantity, avg_cost: h.avg_cost, asset_class: h.asset_class, sector: h.sector,
        price: price, change_pct: q ? q.change_pct : null, is_closed: false, value: value, cost: cost, pnl: pnl,
        pnl_pct: pnl !== null && cost ? pnl / cost * 100 : null };
    });
    var tv = 0, tc = 0, tp = 0, anyCost = false, day = 0;
    ps.forEach(function (p) {
      if (p.value !== null) tv += p.value;
      if (p.cost !== null && p.value !== null) { tc += p.cost; tp += p.pnl; anyCost = true; }
      if (p.value !== null && p.change_pct !== null) day += p.value - p.value / (1 + p.change_pct / 100);
    });
    ps.forEach(function (p) { p.weight_pct = p.value !== null && tv ? p.value / tv * 100 : null; });
    ps.sort(function (a, b) { return (b.value || 0) - (a.value || 0); });
    var ranked = ps.filter(function (p) { return p.pnl_pct !== null; }).sort(function (a, b) { return b.pnl_pct - a.pnl_pct; });
    var prev = tv - day;
    return {
      positions: ps,
      totals: { value: tv, cost: anyCost ? tc : null, pnl: anyCost ? tp : null, pnl_pct: anyCost && tc ? tp / tc * 100 : null,
        day_change: day, day_change_pct: prev ? day / prev * 100 : null, count: ps.length },
      by_class: group(ps, "asset_class"), by_sector: group(ps, "sector"),
      top_winners: ranked.filter(function (p) { return p.pnl_pct > 0; }).slice(0, 3),
      top_losers: ranked.slice().reverse().filter(function (p) { return p.pnl_pct < 0; }).slice(0, 3),
      missing_prices: missing,
    };
  }

  // ── Finanzas (misma lógica que finmate/db/finance_repo.py) ──
  function ym(params) {
    var t = SEED.today.split("-");
    var y = parseInt(params.get("anio") || t[0], 10), m = parseInt(params.get("mes") || t[1], 10);
    if (!(m >= 1 && m <= 12)) m = parseInt(t[1], 10);
    return [y, m];
  }
  function prevMonth(y, m) { return m === 1 ? [y - 1, 12] : [y, m - 1]; }
  function inMonth(t, y, m) { var d = t.date.split("-"); return +d[0] === y && +d[1] === m; }
  function listTx(y, m, cat) {
    return S.txs.filter(function (t) { return inMonth(t, y, m) && (!cat || t.category === cat); })
      .sort(function (a, b) { return a.date < b.date ? 1 : a.date > b.date ? -1 : b.id - a.id; });
  }
  function breakdown(y, m) {
    var amounts = {}; CATS.forEach(function (c) { amounts[c] = 0; });
    var gastos = 0, ingresos = 0, count = 0;
    listTx(y, m).forEach(function (t) {
      if (t.amount < 0) { var k = amounts.hasOwnProperty(t.category) ? t.category : "Otros"; amounts[k] += -t.amount; gastos += -t.amount; count++; }
      else ingresos += t.amount;
    });
    return { year: y, month: m, total_gastos: gastos, total_ingresos: ingresos, count: count,
      categories: CATS.map(function (c) { return { name: c, amount: amounts[c], pct: gastos ? amounts[c] / gastos * 100 : 0 }; }) };
  }

  function follows() {
    return {
      temas: S.temas.slice(),
      indicadores: S.indicadores.map(function (code) {
        var m = SEED.catalogo.filter(function (c) { return c.code === code; })[0] || {};
        return { code: code, name: m.name || code, freq: m.freq || "", relevance: m.relevance || "", country: m.country || "" };
      }),
    };
  }

  function chatReply(q) {
    var t = q.toLowerCase();
    if (/portafolio|inversion|cartera|gan/.test(t)) {
      var p = portfolio().totals;
      return "En esta versión de prueba tu portafolio vale US$" + p.value.toFixed(2) + " y la ganancia acumulada es " +
        (p.pnl_pct !== null ? p.pnl_pct.toFixed(1) + "%" : "—") + ". Con el bot conectado te lo explico con datos en vivo.";
    }
    if (/gast|plata|mes/.test(t)) {
      var t0 = SEED.today.split("-"); var b = breakdown(+t0[0], +t0[1]);
      return "Este mes llevas $" + Math.round(b.total_gastos).toLocaleString("es-CL") + " en gastos (" + b.count + " movimientos).";
    }
    return "Esta es la versión de prueba del panel: el chat todavía no está conectado al bot. Cuando el bot esté desplegado, " +
      "aquí te responde el mismo Finmate de WhatsApp.";
  }

  async function handle(url, opts) {
    var u = new URL(url, "https://demo.local");
    var path = u.pathname.replace(/^\/api/, "");
    var method = (opts.method || "GET").toUpperCase();
    var body = {};
    try { body = opts.body ? JSON.parse(opts.body) : {}; } catch (e) {}
    await new Promise(function (r) { setTimeout(r, 120); });  // latencia simulada
    var mo;

    if (path === "/auth/dev-login" && method === "POST") {
      var digits = String(body.phone || "").replace(/[^\d+]/g, "");
      if (digits.replace("+", "").length < 8) return err("Número inválido. Usá el formato +56 9 1234 5678.");
      S.logged = true; S.phone = digits.charAt(0) === "+" ? digits : "+" + digits; save(S); return json(200, { ok: true });
    }
    if (path === "/auth/logout") { S.logged = false; save(S); return json(200, { ok: true }); }
    if (!S.logged) return err("no_autenticado", 401);

    if (path === "/me") return json(200, { id: 1, name: null, phone: maskPhone(S.phone) });

    if (path === "/resumen") {
      var pf = portfolio(); var d = ym(u.searchParams); var pr = prevMonth(d[0], d[1]);
      var cur = breakdown(d[0], d[1]), prev = breakdown(pr[0], pr[1]);
      var top = cur.total_gastos ? cur.categories.slice().sort(function (a, b) { return b.amount - a.amount; })[0] : null;
      return json(200, {
        portfolio: { totals: pf.totals, top_positions: pf.positions.slice(0, 3), top_winners: pf.top_winners },
        watchlist: S.watchlist.map(function (w) { var q = quote(w.symbol) || {}; return { symbol: w.symbol, note: w.note, price: q.price, change_pct: q.change_pct }; }),
        finanzas: { year: d[0], month: d[1], total_gastos: cur.total_gastos, count: cur.count, prev_total_gastos: prev.total_gastos,
          diff: cur.total_gastos - prev.total_gastos, top_category: top ? top.name : null },
        seguimientos: follows(), avisos: S.avisos, chat: [],
      });
    }

    if (path === "/portafolio" && method === "GET") return json(200, portfolio());
    if (path === "/portafolio" && method === "POST") {
      var s = sym(body.symbol), qty = num(body.quantity), avg = num(body.avg_cost);
      if (!s) return err("Símbolo inválido (ej: AAPL, BRK.B).");
      if (qty === null || qty <= 0) return err("La cantidad tiene que ser mayor a cero.");
      if (avg !== null && avg <= 0) return err("El precio promedio tiene que ser mayor a cero.");
      var h = S.positions.filter(function (p) { return p.symbol === s; })[0];
      if (h) {
        if (avg !== null && h.avg_cost) h.avg_cost = (h.avg_cost * h.quantity + avg * qty) / (h.quantity + qty);
        else if (avg !== null) h.avg_cost = avg;
        h.quantity += qty;
      } else {
        var c = classify(s);
        h = { symbol: s, quantity: qty, avg_cost: avg, asset_class: c[0], sector: c[1] };
        S.positions.push(h);
      }
      save(S); return json(201, { ok: true, symbol: s, quantity: h.quantity, avg_cost: h.avg_cost });
    }
    if ((mo = path.match(/^\/portafolio\/(.+)$/))) {
      var ps = sym(decodeURIComponent(mo[1]));
      var idx = S.positions.findIndex(function (p) { return p.symbol === ps; });
      if (idx < 0) return err("No tenés esa posición.", 404);
      if (method === "DELETE") { S.positions.splice(idx, 1); save(S); return json(200, { ok: true }); }
      if (method === "PATCH") {
        if (body.asset_class) S.positions[idx].asset_class = body.asset_class;
        if (body.sector) S.positions[idx].sector = String(body.sector).slice(0, 60);
        save(S); return json(200, { ok: true });
      }
    }

    if (path === "/watchlist" && method === "GET") {
      return json(200, { items: S.watchlist.map(function (w) { var q = quote(w.symbol) || {};
        return { symbol: w.symbol, note: w.note, price: q.price, change_pct: q.change_pct, threshold_pct: S.avisos.watchlist_threshold_pct }; }) });
    }
    if (path === "/watchlist" && method === "POST") {
      var ws = sym(body.symbol); if (!ws) return err("Símbolo inválido (ej: NVDA).");
      if (!S.watchlist.some(function (w) { return w.symbol === ws; })) S.watchlist.push({ symbol: ws, note: body.note || null });
      save(S); return json(201, { ok: true, symbol: ws });
    }
    if ((mo = path.match(/^\/watchlist\/(.+)$/)) && method === "DELETE") {
      var ds = sym(decodeURIComponent(mo[1])); var before = S.watchlist.length;
      S.watchlist = S.watchlist.filter(function (w) { return w.symbol !== ds; });
      if (S.watchlist.length === before) return err("Ese activo no estaba en tu watchlist.", 404);
      save(S); return json(200, { ok: true });
    }
    if ((mo = path.match(/^\/mercado\/explicar\/(.+)$/))) {
      var es = sym(decodeURIComponent(mo[1])); var q = quote(es);
      if (!q) return err("No hay datos de " + es + " en la versión de prueba.", 404);
      return json(200, Object.assign({ symbol: es }, q, { news: [{ headline: "Versión de prueba: con el bot desplegado aquí aparecen las noticias reales de " + es, source: "Finmate", url: "" }] }));
    }

    if (path === "/finanzas/categorias") return json(200, { categories: CATS });
    if (path === "/finanzas/resumen") {
      var fd = ym(u.searchParams), fp = prevMonth(fd[0], fd[1]);
      return json(200, { actual: breakdown(fd[0], fd[1]), anterior: breakdown(fp[0], fp[1]) });
    }
    if (path === "/finanzas/movimientos" && method === "GET") {
      var md = ym(u.searchParams), cat = u.searchParams.get("categoria") || null;
      if (cat && CATS.indexOf(cat) < 0) return err("Categoría inválida.");
      return json(200, { items: listTx(md[0], md[1], cat) });
    }
    if (path === "/finanzas/movimientos" && method === "POST") {
      var tipo = String(body.tipo || "gasto").toLowerCase(), amt = num(body.amount), category = body.category || "";
      if (tipo !== "gasto" && tipo !== "ingreso") return err("Tipo inválido (gasto o ingreso).");
      if (amt === null || amt <= 0) return err("El monto tiene que ser mayor a cero.");
      if (tipo === "gasto" && CATS.indexOf(category) < 0) return err("Elegí una categoría.");
      if (tipo === "ingreso" && CATS.indexOf(category) < 0) category = "Otros";
      var tx = { id: S.nextId++, date: body.date || SEED.today, amount: tipo === "gasto" ? -Math.abs(amt) : Math.abs(amt),
        category: category, description: String(body.description || "").trim().slice(0, 500),
        occasion: String(body.occasion || "").trim().slice(0, 200), merchant: String(body.merchant || "").trim().slice(0, 200),
        tipo: tipo, has_receipt: false, receipt_url: "" };
      S.txs.push(tx); save(S); return json(201, tx);
    }
    if ((mo = path.match(/^\/finanzas\/movimientos\/(\d+)$/))) {
      var id = +mo[1]; var t = S.txs.filter(function (x) { return x.id === id; })[0];
      if (!t) return err("Movimiento no encontrado.", 404);
      if (method === "DELETE") { S.txs = S.txs.filter(function (x) { return x.id !== id; }); save(S); return json(200, { ok: true }); }
      if (method === "PATCH") {
        if ("category" in body) { if (CATS.indexOf(body.category) < 0) return err("Categoría inválida."); t.category = body.category; }
        ["occasion", "description", "merchant"].forEach(function (k) { if (k in body) t[k] = String(body[k] || "").trim(); });
        save(S); return json(200, t);
      }
    }

    if (path === "/personalidad" && method === "GET") return json(200, S.personalidad);
    if (path === "/personalidad" && method === "PUT") {
      var ch = {};
      for (var i = 0; i < PINT.length; i++) {
        var k = PINT[i]; if (k in body) { var v = parseInt(body[k], 10);
          if (isNaN(v) || v < 1 || v > 10) return err(k + " tiene que estar entre 1 y 10."); ch[k] = v; }
      }
      if ("tono" in body) { if (TONOS.indexOf(body.tono) < 0) return err("Tono inválido (profesional, casual o amigo)."); ch.tono = body.tono; }
      if (!Object.keys(ch).length) return err("No hay nada para cambiar.");
      Object.assign(S.personalidad, ch); save(S); return json(200, S.personalidad);
    }

    if (path === "/seguimientos" && method === "GET") return json(200, Object.assign(follows(), { catalogo: SEED.catalogo }));
    if (path === "/seguimientos" && method === "POST") {
      var st = String(body.tipo || "").toLowerCase().trim(), sv = String(body.valor || "").trim().slice(0, 200);
      if (!sv) return err("Falta qué seguir.");
      if (st === "indicador") {
        var code = sv.toUpperCase();
        if (!SEED.catalogo.some(function (c) { return c.code === code; })) return err("Indicador desconocido.");
        if (S.indicadores.indexOf(code) < 0) S.indicadores.push(code);
      } else {
        if (NEWS_TIPOS.indexOf(st) < 0) st = "keyword";
        if (st === "ticker") sv = sv.toUpperCase();
        if (!S.temas.some(function (x) { return x.tipo === st && x.valor === sv; })) S.temas.push({ tipo: st, valor: sv });
      }
      save(S); return json(201, follows());
    }
    if (path === "/seguimientos" && method === "DELETE") {
      var dt = String(body.tipo || "").toLowerCase().trim(), dv = String(body.valor || "").trim(), ok = false;
      if (dt === "indicador") { var n0 = S.indicadores.length; S.indicadores = S.indicadores.filter(function (c) { return c !== dv.toUpperCase(); }); ok = S.indicadores.length < n0; }
      else { var n1 = S.temas.length; S.temas = S.temas.filter(function (x) { return !(x.tipo === dt && x.valor === dv); }); ok = S.temas.length < n1; }
      if (!ok) return err("No lo estabas siguiendo.", 404);
      save(S); return json(200, follows());
    }

    if (path === "/avisos" && method === "GET") return json(200, S.avisos);
    if (path === "/avisos" && method === "PUT") {
      if ("watchlist_threshold_pct" in body) {
        var thr = num(body.watchlist_threshold_pct);
        if (thr === null || thr < 0.5 || thr > 50) return err("El umbral tiene que estar entre 0,5% y 50%.");
        S.avisos.watchlist_threshold_pct = thr;
      }
      if ("weekly_summary_enabled" in body) S.avisos.weekly_summary_enabled = !!body.weekly_summary_enabled;
      save(S); return json(200, S.avisos);
    }

    if (path === "/feedback" && method === "POST") {
      var ftipos = { idea: "💡 Idea", problema: "🐞 Problema", me_gusta: "❤️ Me gusta", otro: "💬 Otro" };
      var fmsg = String(body.message || "").trim();
      if (!ftipos[body.tipo]) return err("Elegí de qué se trata (idea, problema, me gusta u otro).");
      if (fmsg.length < 5) return err("Escribí un poco más para que podamos entenderte.");
      if (fmsg.length > 2000) return err("El mensaje es demasiado largo (máximo 2000 caracteres).");
      if (!realFetch) return err("No se pudo enviar el mensaje.", 502);
      var subject = "[Finmate · versión de prueba] Feedback: " + ftipos[body.tipo] + (body.rating ? " · " + body.rating + "/5" : "");
      try {
        var fr = await realFetch("https://formsubmit.co/ajax/" + SEED.feedbackTo, {
          method: "POST", headers: { "Content-Type": "application/json", "Accept": "application/json" },
          body: JSON.stringify({ _subject: subject, _template: "table", tipo: ftipos[body.tipo],
            experiencia: body.rating ? body.rating + "/5" : "—", mensaje: fmsg,
            contacto: body.contact ? maskPhone(S.phone) + " (versión de prueba)" : "No autorizó contacto",
            origen: location.href }) });
        var fd = {}; try { fd = await fr.json(); } catch (e) {}
        if (fr.ok && String(fd.success) === "true") return json(201, { ok: true });
        if (/activ/i.test(fd.message || "")) return json(201, { ok: true, pending_activation: true });
        return err("No se pudo enviar el mensaje. Probá de nuevo en un rato.", 502);
      } catch (e) {
        return err("No se pudo enviar el mensaje desde aquí (sin conexión con el servicio de correo).", 502);
      }
    }

    if (path === "/chat" && method === "POST") {
      var msg = String(body.message || "").trim();
      if (!msg) return err("Escribí una pregunta.");
      return json(200, { reply: chatReply(msg) });
    }
    return err("Ruta no disponible en la versión de prueba.", 404);
  }

  var realFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function (input, opts) {
    var url = typeof input === "string" ? input : (input && input.url) || "";
    if (url.indexOf("/api/") === 0 || url === "/api") return handle(url, opts || {});
    return realFetch ? realFetch(input, opts) : Promise.reject(new Error("sin red"));
  };
})();
