---
name: TRATO — Prompt de implementación (export)
description: Documento maestro exportable para un agente de código (Claude Code / Cursor / Devin) que debe construir desde cero TRATO, una plataforma B2B de sourcing inteligente y negociación automatizada de compras por volumen. Incluye descripción completa del producto, score de confianza del vendedor, validación de precios anómalos con gate humano, dashboard de decisión, firmas criptográficas Ed25519 con sesión de firma de 15 minutos, arquitectura multiagente, stack híbrido Next.js + Python/FastAPI/LangGraph + Node/Puppeteer con gateway LLM compatible con OpenAI para modelos autoalojados, modelo de datos, API, criterios de aceptación y roadmap por fases.
---

# TRATO — Prompt de implementación

Artefacto de exportación. El prompt limpio, listo para pegar en un agente de código, está en:

- **`PROMPT-IMPLEMENTACION.md`** — documento maestro completo (producto + agentes + stack + configuración + API + criterios de aceptación + roadmap + reglas de trabajo).
- **`NOTAS-TECH-LEAD.md`** — decisiones tomadas, supuestos y riesgos abiertos, para revisión humana. No forma parte del prompt.

## Uso

1. Copia el contenido íntegro de `PROMPT-IMPLEMENTACION.md`.
2. Pégalo como prompt de sistema / instrucciones iniciales del agente implementador.
3. Ejecuta por fases (Fase 0 → Fase 4). No permitas avanzar de fase sin que se cumplan los criterios de aceptación de la sección 9.
4. Mantén `NOTAS-TECH-LEAD.md` como documento de decisiones humanas: los ADRs que genere el agente deben contrastarse contra él.

## Alcance resumido

Plataforma B2B de compras por volumen que perfila a la empresa —incluida la carga de su situación financiera vía CSV—, busca ofertas multi-plataforma vía scraping, puntúa la confianza de cada vendedor a partir de su antigüedad, ventas, catálogo y reseñas, filtra precios anómalos con bandas estadísticas configurables, negocia precios de forma autónoma en el chat del vendedor con Puppeteer, contrasta cada oferta contra la capacidad financiera real de la empresa en EUR/USD/CNY y presenta los tratos finales en un dashboard donde un responsable humano decide, con firma criptográfica Ed25519 en sesión de firma de 15 minutos, qué ofertas seguir y comprar.

## Puntos clave que el implementador no debe suavizar

1. La confianza del vendedor es un cálculo determinista y versionado, no un juicio del LLM, y acompaña a cada oferta y a cada decisión firmada.
2. El control de precios anómalos ocurre **antes** de negociar: no se gasta presupuesto de negociación en ofertas fuera de rango.
3. Precio anómalamente barato + vendedor de baja confianza se escala de severidad, no se compensa.
4. Ninguna decisión avanza sin registro firmado verificable; el log de auditoría es una cadena de hashes en almacenamiento WORM.
5. La sesión de firma de 15 minutos reduce fricción, no el listón: caduca de forma fija, no deslizante, y los importes altos exigen reautenticación inmediata.
6. El acceso a modelos es HTTP compatible con OpenAI (`/v1/chat/completions`), sin endpoints propietarios, para permitir despliegue autoalojado.

