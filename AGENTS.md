---
name: TRATO — Prompt de implementación (export)
description: Documento maestro exportable para un agente de código (Claude Code / Cursor / Devin) que debe construir desde cero TRATO, una plataforma B2B de sourcing inteligente y negociación automatizada de compras por volumen. Incluye descripción completa del producto, arquitectura multiagente, stack híbrido Next.js + Python/FastAPI/LangGraph + Node/Puppeteer, modelo de datos, API, criterios de aceptación y roadmap por fases.
---

# TRATO — Prompt de implementación

Artefacto de exportación. El prompt limpio, listo para pegar en un agente de código, está en:

- **`PROMPT-IMPLEMENTACION.md`** — documento maestro completo (producto + agentes + stack + API + criterios de aceptación + roadmap + reglas de trabajo).
- **`NOTAS-TECH-LEAD.md`** — decisiones tomadas, supuestos y riesgos abiertos, para revisión humana. No forma parte del prompt.

## Uso

1. Copia el contenido íntegro de `PROMPT-IMPLEMENTACION.md`.
2. Pégalo como prompt de sistema / instrucciones iniciales del agente implementador.
3. Ejecuta por fases (Fase 0 → Fase 4). No permitas avanzar de fase sin que se cumplan los criterios de aceptación de la sección 8.
4. Mantén `NOTAS-TECH-LEAD.md` como documento de decisiones humanas: los ADRs que genere el agente deben contrastarse contra él.

## Alcance resumido

Plataforma B2B de compras por volumen que perfila a la empresa, busca ofertas multi-plataforma vía scraping, negocia precios de forma autónoma en el chat del vendedor con Puppeteer, contrasta cada oferta contra la capacidad financiera real de la empresa y devuelve una recomendación final explicable y priorizada por perfil.
