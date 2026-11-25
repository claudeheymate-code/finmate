/* Finmate — idioma del panel (español / inglés).
   El panel está escrito en español. Si el usuario elige inglés en Ajustes,
   este script traduce en el navegador los textos visibles (y placeholder,
   aria-label, title y alt), incluso los que panel.js agrega después
   (MutationObserver). Se carga en <head>, antes de que se pinte la página,
   para que no se vea un parpadeo en español.
   La preferencia se guarda en este dispositivo (localStorage "finmate-lang").
   Para agregar un texto nuevo: sumarlo a DICT (texto exacto) o a RULES
   (textos que llevan números o nombres adentro). */
(function () {
  "use strict";
  var KEY = "finmate-lang";
  function stored() { try { return localStorage.getItem(KEY) === "en" ? "en" : "es"; } catch (e) { return "es"; } }
  var lang = stored();
  document.documentElement.lang = lang;

  var DICT = {
    "Tus noticias": "Your news",
    "Emojis": "Emojis",
    "Cuántos emojis usa en mensajes y listas (1-2 = ninguno)": "How many emojis it uses in messages and lists (1-2 = none)",
    "Nivel 3 · muy relevante": "Level 3 · very relevant",
    "Nivel 2 · algo relevante": "Level 2 · somewhat relevant",
    "Nivel 1 · poco relevante": "Level 1 · not very relevant",
    "Lo más importante para ti": "What matters most to you",
    "Vale la pena saberlo, sin apuro": "Worth knowing, no rush",
    "Lo que no te suele interesar": "What you usually don't care about",
    "Por el chat": "In the chat",
    "En el resumen": "In the summary",
    "Solo si pregunto": "Only if I ask",
    "Cada vez menos": "Less and less",
    "Siempre en el resumen": "Always in the summary",
    "Lo que he aprendido de ti": "What I've learned about you",
    "Fijar un tema": "Pin a topic",
    "Fijar": "Pin",
    "Automático": "Automatic",
    "Aprendiendo": "Learning",
    "Aprendido": "Learned",
    "Fijado por ti": "Pinned by you",
    "Ya no te lo muestro": "No longer shown",
    "Listo, quedó fijado.": "Done, it's pinned.",
    "Todavía no calificas noticias. Por ahora te llegan como siempre.": "You haven't rated any news yet. For now they arrive as usual.",
    // Navegación y barra superior
    "Resumen": "Overview", "Inversiones": "Investments", "Gastos": "Expenses", "Ajustes": "Settings", "Feedback": "Feedback",
    "Mis inversiones": "My investments", "Mis gastos": "My expenses", "Ajustes y personalidad": "Settings and personality",
    "Secciones": "Sections", "Acciones rápidas": "Quick actions", "Agregar posición": "Add position", "Registrar gasto": "Log expense",
    "Seguir activo": "Follow asset", "Ajustar avisos": "Adjust alerts", "Cerrar sesión": "Log out", "Enviar pregunta": "Send question",
    "Pregúntale a Finmate": "Ask Finmate", "Pregúntale a Finmate… ej: ¿por qué bajó Apple hoy?": "Ask Finmate… e.g. why did Apple drop today?",
    "Pensando…": "Thinking…", "Cerrar": "Close", "Cargando…": "Loading…", "Algo falló. Intenta de nuevo.": "Something went wrong. Please try again.",
    "no_autenticado": "Not signed in",
    // Acceso
    "Finmate — Entrar": "Finmate — Sign in", "Entrar": "Sign in", "Entrar al panel": "Go to dashboard", "Tu número de WhatsApp": "Your WhatsApp number",
    "Tu asistente financiero, ahora también en la web": "Your financial assistant, now on the web too",
    "Mira tu portafolio, tus gastos y tus alertas de un vistazo. Lo que cambies acá se refleja en tu chat de WhatsApp.": "See your portfolio, expenses and alerts at a glance. Whatever you change here shows up in your WhatsApp chat.",
    "Modo desarrollo: se entra solo con el número. El acceso con código por WhatsApp llega en la etapa 4.": "Development mode: sign in with just your number. WhatsApp code sign-in comes in stage 4.",
    "El acceso con un código que te llega por WhatsApp se está terminando. Mientras tanto, sigue usando Finmate desde el chat.": "Sign-in with a code sent to your WhatsApp is almost ready. In the meantime, keep using Finmate from the chat.",
    "Número inválido. Usa el formato +56 9 1234 5678.": "Invalid number. Use the format +56 9 1234 5678.",
    // Resumen
    "Tu plata, de un vistazo": "Your money at a glance", "Sincronizado con WhatsApp": "Synced with WhatsApp", "Tus activos": "Your assets",
    "Principales posiciones y tu watchlist": "Top positions and your watchlist", "Ver todo": "See all", "Ver todos": "See all",
    "Lo último en WhatsApp": "Latest on WhatsApp", "El panel y el chat comparten la misma memoria": "The dashboard and the chat share the same memory",
    "Indicadores y temas de noticias": "Indicators and news topics", "Valor del portafolio": "Portfolio value", "Ganancia total": "Total gain",
    "Alertas activas": "Active alerts", "Todavía no has cargado posiciones": "You haven't added any positions yet",
    "Carga el precio promedio para calcularla": "Add your average price to calculate it", "Sigue un activo para recibir alertas": "Follow an asset to get alerts",
    "En tu watchlist": "On your watchlist", "Agrega posiciones o sigue activos desde Mis inversiones.": "Add positions or follow assets from My investments.",
    "Todavía no hay conversación. Escríbele a Finmate por WhatsApp o desde la barra de arriba.": "No conversation yet. Message Finmate on WhatsApp or from the bar above.",
    "Indicador": "Indicator", "Siguiendo": "Following", "No sigues nada todavía. Agrégalo en Ajustes.": "You're not following anything yet. Add it in Settings.",
    // Inversiones
    "Portafolio": "Portfolio", "Ganancia y pérdida calculadas con el último precio": "Gains and losses calculated with the latest price",
    "Top 3 ganadoras": "Top 3 winners", "Top 3 perdedoras": "Top 3 losers", "Mayor ganancia desde que compraste": "Biggest gain since you bought",
    "Mayor pérdida desde que compraste": "Biggest loss since you bought", "Renta fija vs renta variable": "Fixed income vs equities",
    "Cómo se reparte tu plata por tipo de activo": "How your money is split by asset type", "Por sector": "By sector",
    "Dónde está concentrado tu riesgo": "Where your risk is concentrated", "Posiciones": "Positions", "Símbolo": "Symbol", "Cantidad": "Quantity",
    "Costo promedio": "Average cost", "Precio": "Price", "Hoy": "Today", "Valor": "Value", "Ganancia": "Gain", "Peso": "Weight", "Activo": "Asset",
    "Acciones": "Actions", "Valor total": "Total value", "Invertido": "Invested", "Tipo de activo": "Asset type", "Sectores": "Sectors",
    "Agregar o actualizar posición": "Add or update a position", "Si ya la tienes, se suma y se recalcula el costo promedio": "If you already have it, it's added and the average cost is recalculated",
    "Precio promedio (USD)": "Average price (USD)", "(opcional)": "(optional)", "Agregar": "Add", "Ej: VOO": "e.g. VOO", "Ej: 5": "e.g. 5", "Ej: 410.50": "e.g. 410.50", "Ej: AMZN": "e.g. AMZN",
    "También puedes escribirle al bot: “agrega 5 VOO a 410,50”.": "You can also message the bot: “add 5 VOO at 410.50”.",
    "Watchlist": "Watchlist", "Activos que sigues sin tenerlos": "Assets you follow without owning them", "Seguir un activo nuevo": "Follow a new asset",
    "Seguir": "Follow", "¿Por qué se movió?": "Why did it move?", "Buscando noticias…": "Looking for news…",
    "No encontré noticias recientes que hablen de este activo.": "I couldn't find recent news about this asset.",
    "No sigues ningún activo todavía.": "You're not following any assets yet.", "Listo, posición guardada.": "Done, position saved.",
    "Ninguna posición en ganancia todavía.": "No positions in profit yet.", "Ninguna posición en pérdida. Bien ahí.": "No positions at a loss. Nice.",
    "Todavía no has cargado posiciones. Usa el formulario de abajo o escríbele al bot.": "You haven't added any positions yet. Use the form below or message the bot.",
    "No tienes esa posición.": "You don't have that position.",
    "Renta variable": "Equities", "Renta fija": "Fixed income", "Tecnología": "Technology", "Índice amplio": "Broad index", "Bonos": "Bonds",
    "Financiero": "Financials", "Consumo": "Consumer", "Comunicaciones": "Communications", "Energía": "Energy", "Salud": "Healthcare",
    "Industrial": "Industrials", "Inmobiliario": "Real estate", "Materiales": "Materials", "Servicios básicos": "Utilities", "Sin clasificar": "Unclassified", "Otro": "Other",
    // Gastos
    "Finanzas personales": "Personal finance", "Este mes": "This month", "En lo que va del año": "Year to date", "Gastos desde el 1 de enero": "Expenses since January 1",
    "Este mes vs. mes pasado": "This month vs. last month", "Por categoría, una al lado de la otra": "By category, side by side",
    "Toca una categoría para ver sus gastos": "Tap a category to see its expenses", "Toca un gasto para ver el detalle": "Tap an expense to see the details",
    "Toca un gasto para ver el detalle y cambiarle la categoría.": "Tap an expense to see the details and change its category.",
    "Categoría": "Category", "Lst Mth": "Lst Mth", "Dif.": "Diff.", "Diferencia": "Difference", "Total": "Total", "Todos los gastos": "All expenses",
    "Mes anterior": "Previous month", "Vas gastando más que el mes pasado": "You're spending more than last month",
    "Vas gastando menos que el mes pasado": "You're spending less than last month", "Registrar un gasto": "Log an expense",
    "Cuéntanos la ocasión y elige la categoría. Pronto podrás subir la foto de la boleta y Finmate leerá el monto solo.": "Tell us the occasion and pick the category. Soon you'll be able to upload a photo of the receipt and Finmate will read the amount for you.",
    "Foto de la boleta": "Receipt photo", "Próximamente: la lectura automática llega en la etapa 5": "Coming soon: automatic reading arrives in stage 5",
    "Monto (CLP)": "Amount (CLP)", "¿Cuál fue la ocasión?": "What was the occasion?", "Descripción": "Description", "Guardar gasto": "Save expense",
    "Ej: 12990": "e.g. 12990", "Ej: cumpleaños de la Cata": "e.g. Cata's birthday", "Ej: regalo": "e.g. gift", "Ej: Bencina": "e.g. Gas",
    "También por WhatsApp: “gasté 8 lucas en el almuerzo”": "Also on WhatsApp: “I spent 8k on lunch”",
    "Mis categorías": "My categories", "Elige las que usas y agrega las tuyas. Solo cambian en tu cuenta.": "Pick the ones you use and add your own. They only change for your account.",
    "Nueva categoría": "New category", "Siempre disponible": "Always available", "Editar": "Edit", "Gasto": "Expense", "Boleta": "Receipt",
    "Este gasto no tiene foto de boleta.": "This expense has no receipt photo.", "Comercio": "Merchant", "Ocasión": "Occasion",
    "Al cambiarla, la torta se actualiza.": "Changing it updates the chart.", "Borrar gasto": "Delete expense", "¿Borrar este gasto? No se puede deshacer.": "Delete this expense? This can't be undone.",
    "Elige una categoría.": "Pick a category.", "Sin datos todavía": "No data yet", "Distribución": "Breakdown",
    "Comidas": "Meals", "Carretes": "Nights out", "Asados": "BBQs", "Regalos": "Gifts", "Suscripciones": "Subscriptions", "Polola": "Girlfriend",
    "Copete": "Drinks", "Bets": "Bets", "Otros": "Other", "Evento Social": "Social event", "Viajes": "Travel", "Vivienda": "Housing",
    "Alimentación": "Groceries", "Transporte": "Transport", "Ocio": "Leisure", "Educación": "Education",
    // Ajustes
    "Tu Finmate, a tu manera": "Your Finmate, your way", "Personalidad del bot": "Bot personality", "Cambia cómo te habla, nunca la calidad del análisis": "Changes how it talks to you, never the quality of the analysis",
    "Humor": "Humor", "Qué tan relajado y gracioso es": "How relaxed and funny it is", "Sarcasmo": "Sarcasm", "Un toque de ironía cuando el mercado se pone dramático": "A touch of irony when the market gets dramatic",
    "Frecuencia de chistes": "Joke frequency", "Cada cuánto mete un chiste": "How often it cracks a joke", "Nivel conversador": "Chattiness",
    "Respuestas cortas o con más contexto": "Short answers or more context", "Tono": "Tone", "Profesional": "Professional", "Casual": "Casual", "Amigo": "Friend",
    "Guardar cambios": "Save changes", "Así te respondería": "How it would reply", "Vista previa aproximada con tu configuración": "Approximate preview with your settings",
    "¿cómo va mi portafolio hoy?": "how's my portfolio doing today?", "Guardado. El bot ya te habla así.": "Saved. The bot now talks to you like this.",
    "Lo que sigues": "What you follow", "Temas de noticias e indicadores económicos": "News topics and economic indicators", "Temas de noticias": "News topics",
    "Indicadores": "Indicators", "Tipo": "Type", "Indicador económico": "Economic indicator", "Empresa (ticker)": "Company (ticker)", "Sector": "Sector",
    "País": "Country", "Palabra clave": "Keyword", "Qué seguir": "What to follow", "Ninguno": "None", "Ej: bancos regionales": "e.g. regional banks",
    "Avisos": "Alerts", "Cuándo te escribe Finmate": "When Finmate messages you", "Umbral de alertas de watchlist": "Watchlist alert threshold",
    "Te avisa si un activo se mueve más que esto en el día": "Alerts you if an asset moves more than this in a day", "Umbral en porcentaje": "Threshold in percent",
    "Noticias de tus activos": "News about your assets", "Máximo de avisos por día (0 = ninguno)": "Max alerts per day (0 = none)",
    "Resultados de empresas": "Company earnings", "Cuando una empresa publica sus resultados trimestrales": "When a company reports quarterly results",
    "Solo mis activos": "Only my assets", "Todas las empresas": "All companies", "Ninguno": "None",
    "Datos macroeconómicos": "Economic data", "Inflación, empleo, tasas y otros datos apenas se publican": "Inflation, jobs, rates and other data as soon as they are released",
    "Noticias generales del mercado": "General market news", "Las noticias más importantes del día, aunque no sean de tus activos": "The day's top stories, even if they are not about your assets",
    "Resumen semanal": "Weekly summary", "Domingos a las 20:00 (hora de Chile)": "Sundays at 8:00 PM (Chile time)", "Activado": "On",
    "WhatsApp vinculado": "Linked WhatsApp", "Conectado": "Connected", "Guardar avisos": "Save alerts", "Avisos guardados.": "Alerts saved.",
    "Idioma de la app": "App language", "Cómo ves los textos del panel en este dispositivo": "How the dashboard text is shown on this device",
    "El bot de WhatsApp sigue respondiendo en español.": "The WhatsApp bot still replies in Spanish.", "Idioma guardado.": "Language saved.",
    "Decisión de tasa Fed": "Fed rate decision", "Inflación EE.UU. (CPI)": "US inflation (CPI)", "Nóminas no agrícolas (NFP)": "Nonfarm payrolls (NFP)",
    "PIB EE.UU.": "US GDP", "Inflación PCE EE.UU.": "US PCE inflation", "Desempleo EE.UU.": "US unemployment", "Ventas minoristas EE.UU.": "US retail sales",
    "ISM Manufacturero": "ISM Manufacturing", "Minutas FOMC": "FOMC minutes", "IPC Chile": "Chile CPI", "PIB Chile (Imacec)": "Chile GDP (Imacec)",
    "Tasa Banco Central de Chile": "Central Bank of Chile rate", "Desempleo Chile": "Chile unemployment", "Precio del cobre": "Copper price", "Dólar / Peso chileno": "US dollar / Chilean peso",
    // Feedback
    "Ayúdanos a mejorar Finmate": "Help us improve Finmate", "Cuéntanos": "Tell us", "Tu mensaje le llega directo al equipo de Finmate": "Your message goes straight to the Finmate team",
    "¿De qué se trata?": "What's it about?", "💡 Idea": "💡 Idea", "🐞 Problema": "🐞 Problem", "❤️ Me gusta": "❤️ I like it", "💬 Otro": "💬 Other",
    "¿Cómo ha sido tu experiencia?": "How has your experience been?", "Muy mala": "Very bad", "Mala": "Bad", "Normal": "OK", "Buena": "Good", "Excelente": "Excellent",
    "Tu mensaje": "Your message", "Ej: me gustaría que el resumen semanal llegara los lunes en la mañana…": "e.g. I'd like the weekly summary to arrive on Monday mornings…",
    "Pueden escribirme por WhatsApp si necesitan más detalles": "You can message me on WhatsApp if you need more details", "Enviar feedback": "Send feedback",
    "Enviando…": "Sending…", "¡Gracias! Tu mensaje ya le llegó al equipo de Finmate.": "Thanks! Your message has reached the Finmate team.",
    "Cada idea que nos cuentas nos ayuda a hacer Finmate más a tu medida.": "Every idea you share helps us make Finmate more yours.",
    "Elige de qué se trata (idea, problema, me gusta u otro).": "Pick what it's about (idea, problem, like or other).",
    "Escribe un poco más para que podamos entenderte.": "Write a bit more so we can understand you.", "Escribe una pregunta.": "Write a question.",
    "El mensaje es demasiado largo (máximo 2000 caracteres).": "The message is too long (2,000 characters max).",
    "No se pudo enviar el mensaje.": "The message couldn't be sent.", "No se pudo enviar el mensaje. Intenta de nuevo en un rato.": "The message couldn't be sent. Try again in a bit.",
    // Demo pública
    "Versión de prueba · datos de ejemplo": "Demo version · sample data", "Reiniciar": "Reset"
  };
  var MES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"];
  var MON = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  function month(s) {  // "noviembre" / "Noviembre" / "nov" / "Nov" -> inglés
    var l = s.toLowerCase();
    for (var i = 0; i < 12; i++) {
      if (l === MES[i]) return MON[i];
      if (l === MES[i].slice(0, 3)) return MON[i].slice(0, 3);
    }
    return s;
  }
  var MRE = "(enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|Enero|Febrero|Marzo|Abril|Mayo|Junio|Julio|Agosto|Septiembre|Octubre|Noviembre|Diciembre)";
  var MSHORT = "(ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|Ene|Feb|Mar|Abr|May|Jun|Jul|Ago|Sep|Oct|Nov|Dic)";
  function t(s) { var r = tr(s); return r == null ? s : r; }
  var FREQ = { "mensual": "monthly", "trimestral": "quarterly", "diario": "daily", "~8 veces/año": "~8 times/year", "alta": "high", "media": "medium", "baja": "low" };
  var RULES = [
    [/^Finmate — (.+)$/, function (m, a) { return "Finmate — " + t(a); }],
    [/^(.+) · Finmate \(prueba\)$/, function (m, a) { return t(a) + " · Finmate (demo)"; }],
    [/^(.+) hoy \((.+)\)$/, "$1 today ($2)"],
    [/^(.+) sobre lo invertido$/, "$1 on what you invested"],
    [/^Gastos de (\S+)$/, function (m, a) { return month(a) + " expenses"; }],
    [/^Gastado en (\S+)$/, function (m, a) { return "Spent in " + month(a); }],
    [/^(\d+) gastos registrados$/, function (m, n) { return n + (n === "1" ? " expense logged" : " expenses logged"); }],
    [/^(.+) menos que el mes pasado(.*)$/, function (m, a, r) { return a + " less than last month" + rest(r); }],
    [/^(.+) más que el mes pasado(.*)$/, function (m, a, r) { return a + " more than last month" + rest(r); }],
    [/^(\d+ gastos registrados)( · .*)$/, function (m, a, r) { return t(a) + rest(r); }],
    [/^Watchlist, si algo se mueve más de (.+)$/, "Watchlist, if something moves more than $1"],
    [/^En tu portafolio · (.+) u\.$/, "In your portfolio · $1 sh."],
    [/^(.+) · relevancia (.+)$/, function (m, f, r) { return (FREQ[f] || f) + " · " + (FREQ[r] || r) + " relevance"; }],
    [/^Tema de noticias · (.+)$/, function (m, a) { return "News topic · " + (TIPO[a] || a); }],
    [/^(\d+) (grupo|grupos)$/, function (m, n) { return n + (n === "1" ? " group" : " groups"); }],
    [/^(\d+) (sector|sectores)$/, function (m, n) { return n + (n === "1" ? " sector" : " sectors"); }],
    [/^Sin precio ahora para: (.+)\. No cuentan en los totales\.$/, "No price right now for: $1. They're not counted in the totals."],
    [/^Quitar (.+) del portafolio$/, "Remove $1 from portfolio"],
    [/^¿Quitar (.+) de tu portafolio\?$/, "Remove $1 from your portfolio?"],
    [/^Actualizado (.+)$/, "Updated $1"],
    [/^Aviso si se mueve más de (.+) en el día$/, "Alert if it moves more than $1 in a day"],
    [/^Dejar de seguir (.+)$/, function (m, a) { return "Unfollow " + t(a); }],
    // Descripción de las tortas para lectores de pantalla: "Sectores: Tecnología 37,9%, Bonos 21,4%"
    [/^([^:]+): ((?:[^,]+ [\d.,]+%)(?:, [^,]+ [\d.,]+%)*)$/, function (m, label, list) {
      return t(label) + ": " + list.split(", ").map(function (it) { var k = it.lastIndexOf(" "); return t(it.slice(0, k)) + it.slice(k); }).join(", ");
    }],
    [new RegExp("^" + MRE + " (\\d{4})$"), function (m, a, y) { return month(a) + " " + y; }],
    [new RegExp("^" + MSHORT + "$"), function (m, a) { return month(a); }],
    [new RegExp("^(\\d{1,2}) " + MSHORT + "$"), function (m, d, a) { return month(a) + " " + d; }],
    [/^En lo que va de (\d{4})$/, "$1 year to date"],
    [/^Total (\d{4})$/, "Total $1"],
    [/^Gastos en (.+)$/, function (m, a) { return "Expenses in " + t(a); }],
    [/^No hay gastos en esta categoría este mes\.$/, "No expenses in this category this month."],
    [/^No hay gastos este mes\.$/, "No expenses this month."],
    [/^Listo: el gasto quedó en (.+) y la torta se actualizó\.$/, function (m, a) { return "Done: the expense was saved under " + t(a) + " and the chart was updated."; }],
    [/^Listo: (.+) ya aparece para registrar gastos\.$/, "Done: $1 is now available for logging expenses."],
    [/^Sacar (.+)$/, function (m, a) { return "Remove " + t(a); }],
    [/^Usar (.+)$/, function (m, a) { return "Use " + t(a); }],
    [/^(.+) · los cambios se sincronizan con el chat$/, "$1 · changes sync with the chat"]
  ];
  var TIPO = { "ticker": "ticker", "sector": "sector", "pais": "country", "keyword": "keyword", "indicador": "indicator" };
  function rest(r) {  // " · más en Comidas"
    if (!r) return "";
    var m = /^ · más en (.+)$/.exec(r);
    return m ? " · most on " + t(m[1]) : r;
  }
  function tr(s) {
    if (DICT.hasOwnProperty(s)) return DICT[s];
    for (var i = 0; i < RULES.length; i++) {
      var r = RULES[i];
      if (r[0].test(s)) {
        var out = s.replace(r[0], r[1]);
        if (out !== s) return out;
      }
    }
    if (s.indexOf(" · ") > 0) {
      var parts = s.split(" · "), changed = false;
      var outp = parts.map(function (p) { var x = tr(p); if (x != null && x !== p) { changed = true; return x; } return p; });
      if (changed) return outp.join(" · ");
    }
    return null;
  }

  // ---------- aplicar al DOM ----------
  var ATTRS = ["placeholder", "aria-label", "title", "alt"];
  var textRec = new WeakMap();   // nodo de texto -> {es, en}
  var attrRec = new WeakMap();   // elemento -> {attr: {es, en}}
  function skip(el, forText) {
    for (var e = el; e && e.nodeType === 1; e = e.parentNode) {
      var n = e.nodeName;
      if (n === "SCRIPT" || n === "STYLE" || n === "NOSCRIPT") return true;
      if (forText && n === "TEXTAREA") return true;  // lo que escribe el usuario no se toca
      if (e.hasAttribute("data-no-i18n")) return true;
    }
    return false;
  }
  function split(s) { var m = /^(\s*)([\s\S]*?)(\s*)$/.exec(s); return m; }
  function doText(node) {
    var data = node.data;
    if (!data || !/[A-Za-zÁÉÍÓÚáéíóúñ]/.test(data)) return;
    var rec = textRec.get(node);
    if (lang === "en") {
      if (rec && data === rec.en) return;
      var m = split(data); var en = tr(m[2]);
      if (en == null) { if (rec) textRec.delete(node); return; }
      rec = { es: data, en: m[1] + en + m[3] };
      textRec.set(node, rec);
      if (rec.en !== data) node.data = rec.en;
    } else if (rec) {
      if (data === rec.en) node.data = rec.es;
      textRec.delete(node);
    }
  }
  function doAttrs(el) {
    var recs = attrRec.get(el);
    for (var i = 0; i < ATTRS.length; i++) {
      var a = ATTRS[i]; if (!el.hasAttribute(a)) continue;
      var v = el.getAttribute(a); var r = recs && recs[a];
      if (lang === "en") {
        if (r && v === r.en) continue;
        var en = tr(v.trim());
        if (en == null) continue;
        recs = recs || {}; recs[a] = { es: v, en: en }; attrRec.set(el, recs);
        if (en !== v) el.setAttribute(a, en);
      } else if (r) {
        if (v === r.en) el.setAttribute(a, r.es);
        delete recs[a];
      }
    }
  }
  function walk(root) {
    if (!root) return;
    if (root.nodeType === 3) { if (!skip(root.parentNode, true)) doText(root); return; }
    if (root.nodeType !== 1 && root.nodeType !== 9) return;
    if (root.nodeType === 1) { if (skip(root)) return; doAttrs(root); }
    var w = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) { return (n.nodeType === 1 ? skip(n) : skip(n.parentNode, true)) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT; }
    });
    var n; while ((n = w.nextNode())) { if (n.nodeType === 3) doText(n); else doAttrs(n); }
  }
  var busy = false;
  var mo = new MutationObserver(function (muts) {
    if (busy) return; busy = true;
    try {
      for (var i = 0; i < muts.length; i++) {
        var m = muts[i];
        if (m.type === "characterData") { if (!skip(m.target.parentNode, true)) doText(m.target); }
        else if (m.type === "attributes") { if (!skip(m.target)) doAttrs(m.target); }
        else for (var j = 0; j < m.addedNodes.length; j++) walk(m.addedNodes[j]);
      }
    } finally { busy = false; mo.takeRecords(); }
  });
  function observe() {
    mo.observe(document.documentElement, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ATTRS });
  }
  if (lang === "en") observe();

  // Los avisos del navegador (confirm) también se traducen
  var nativeConfirm = window.confirm;
  window.confirm = function (msg) { return nativeConfirm.call(window, lang === "en" ? (tr(String(msg)) || msg) : msg); };

  function setLang(next) {
    next = next === "en" ? "en" : "es";
    try { localStorage.setItem(KEY, next); } catch (e) {}
    if (next === lang) return;
    lang = next; document.documentElement.lang = next;
    mo.disconnect();
    walk(document.documentElement);
    if (next === "en") observe();
    document.dispatchEvent(new CustomEvent("finmate:lang", { detail: next }));
  }

  window.FinmateI18n = { _tr: tr, get: function () { return lang; }, set: setLang, t: function (s) { return lang === "en" ? (tr(s) || s) : s; } };
})();
