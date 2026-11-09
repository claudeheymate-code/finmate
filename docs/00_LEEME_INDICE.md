# Finmate — Índice de documentación

Carpeta con todo el contexto del proyecto (plan, checklist, estado, ideas, plantillas),
pensada para trabajar con Claude Code. Consolidado el 29 oct 2026 desde el proyecto
"Finmate" de claude.ai y los artifacts publicados.

## Empezá por acá

| Archivo | Qué tiene | Cuándo leerlo |
|---|---|---|
| `../CLAUDE.md` (raíz) | Resumen vivo del proyecto: estado, arquitectura, variables de entorno | Siempre primero — Claude Code lo carga solo |
| `03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md` | Qué está hecho, qué falta, bloqueador, equivalencia de fases plan vs. código | Al retomar el trabajo |
| `01_PLAN_ARQUITECTURA_Y_FASES.md` | Plan v2 completo: 11 decisiones técnicas, modelo de datos, restricción WhatsApp, las 9 fases | Para decidir qué construir después |
| `02_CHECKLIST_CONSTRUCCION_POR_FASE.md` | Cada paso de cada fase con su verificación, marcado con el avance real | Al empezar/cerrar una fase |
| `04_BRAINSTORMING_IDEAS.md` | Ideas sueltas a evaluar (no compromisos) | Para agregar ideas nuevas |
| `05_WHATSAPP_TEMPLATES_TWILIO.md` | Los 3 textos de Content Templates listos para Twilio/Meta | Al crear las plantillas |
| `originales_html/` | Las versiones HTML originales del plan y del checklist (con diseño) | Para verlas en el navegador |

## Otros archivos del proyecto (raíz)

- `RESUMEN_CONVERSACION.md` — historial detallado de decisiones de la Fase 0 y sesiones anteriores.
  ⚠️ Contiene API keys y tokens en texto plano y **no** está en `.gitignore`.
- `SETUP.md`, `DEPLOY_GUIDE.md` — guías originales de instalación y deploy.
- `Finmate_Guia_Completa.pdf` / `.docx` — guía de usuario original.
- `Claude outputs/Finmate_Costos.xlsx` — estimación de costos.

## Cómo pedirle cosas a Claude Code

- "Leé `docs/03_ESTADO_ACTUAL_Y_PROXIMOS_PASOS.md` y arrancá la siguiente fase del plan."
- "Implementá la Fase 1 (personalidad) siguiendo `docs/02_CHECKLIST_CONSTRUCCION_POR_FASE.md`."
- "Agregá esta idea a `docs/04_BRAINSTORMING_IDEAS.md`: ..."
- Al terminar cada sesión: "Actualizá `CLAUDE.md` y el checklist con lo que hicimos."
