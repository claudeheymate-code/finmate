# Finmate — Notas de brainstorming

> Fuente: doc `claude/brainstorming.md` del proyecto "Finmate" en claude.ai.

Ideas sueltas que van surgiendo durante el desarrollo, para revisar de vez en cuando y evaluar si vale la pena construirlas. No son compromisos ni roadmap fijo — es una lista viva.

---

## 2026-10-26

### Panel de control web para editar la watchlist
Hoy la watchlist (y el portafolio) solo se edita por WhatsApp, charlando con el bot. Idea: un panel web simple donde el usuario pueda ver/editar la watchlist de forma más rápida que escribiendo mensajes — útil si la lista crece o si quiere gestionarla de un vistazo. Relacionado con el Centro de Control (Fases 1 y 7 del plan), una vez que haya uso real que lo justifique.

### Envío automatizado de reportes con distintos templates
Idea: que el bot pueda mandar reportes periódicos (ej. resumen semanal, estado del portafolio, performance de la watchlist) usando distintas plantillas según el tipo de reporte o la preferencia del usuario. Se conecta con lo que ya existe en `finmate/alerts/engine.py` (resumen semanal, alertas broadcast) pero personalizado por usuario y con formato de reporte configurable.

---

<!-- Agregar nuevas ideas abajo, con fecha, a medida que surjan -->
