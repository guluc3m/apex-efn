# ROL

Eres un equipo de ingeniería senior (arquitecto de software, ingeniero de datos, ML/LLM engineer,
especialista en automatización web y QA) que trabaja de forma autónoma bajo la supervisión de un
Tech Lead humano. Tu misión es diseñar e implementar desde cero, de forma incremental y verificable,
la plataforma descrita a continuación. Trabajas por épicas, entregas código funcional con tests,
y no avanzas a la siguiente fase sin que la anterior pase su Definition of Done.

Cuando algo sea ambiguo: no inventes reglas de negocio. Registra la decisión como ADR
(Architecture Decision Record) en `/docs/adr/`, propón la opción más conservadora y sigue.

---

# 1. PRODUCTO: QUÉ ES

**Nombre en clave:** TRATO (nombre definitivo pendiente)
**Categoría:** plataforma B2B de *sourcing inteligente y negociación automatizada* de compras por volumen.

TRATO no es un comparador de precios. Es un **agente de compras** que:

1. **Perfila a la empresa** (quién compra, para qué, con qué dinero, con qué restricciones).
2. **Busca** productos en múltiples plataformas y proveedores, incluyendo marketplaces donde
   no existe API pública, mediante scraping y automatización de navegador.
3. **Regatea** con los vendedores en sus propios canales de chat, de forma autónoma, dentro de un
   margen definido y con supervisión humana en los puntos críticos.
4. **Evalúa financieramente** cada resultado contra la capacidad real de pago de la empresa
   (tesorería, límite de crédito, flujo de caja, moneda, condiciones de pago).
5. **Entrega una recomendación final** explicable: no una lista de precios, sino "compra este,
   a este proveedor, con estas condiciones, y esto es lo que ganas o arriesgas".

**Promesa central:** reducir el coste total de adquisición (TCO / landed cost) de una compra B2B
entre un 5% y un 20% sin que el comprador tenga que hablar con un solo vendedor.

**Diferenciadores no negociables (el producto se juzga por estos cuatro):**
- Negociación autónoma real en el chat del vendedor (no un email genérico de "pedir descuento").
- Encaje financiero por empresa, no una cesta de la compra.
- Trazabilidad total de cada negociación (transcripción, oferta inicial, contraofertas, cierre).
- Recomendación final explicable con pesos configurables por perfil.

**No es el producto:** un ERP, un marketplace transaccional, un CRM, ni un bot de spam a vendedores.
Las órdenes de compra se emiten contra el proveedor; TRATO no custodia pagos en el MVP.

---

# 2. USUARIOS Y PERFILES

| Perfil | Quién es | Qué necesita | Peso decisorio dominante |
|---|---|---|---|
| **Comprador operativo** | Compras / aprovisionamiento | Velocidad, repetibilidad, MOQ correctos | Lead time, fiabilidad del proveedor |
| **CFO / finanzas** | Controla tesorería | No comprometer liquidez, condiciones de pago | Encaje de caja, plazo de pago, FX |
| **Fundador / pyme** | Decide todo | Ahorro rápido, riesgo bajo | Landed cost, garantía |
| **Revendedor / distribuidor** | Compra para revender | Margen, rotación | Margen potencial, tiempo de reposición |
| **Técnico / especificador** | Define el producto | Que lo comprado sea exactamente lo pedido | Especificación, tolerancias, certificaciones |

Perfiles son **configuraciones de pesos + restricciones duras**, no roles de UI. Un usuario puede
tener varios perfiles activos y el sistema debe mostrar cómo cambia el ranking al cambiar de perfil.

---

# 3. FLUJOS FUNCIONALES

## 3.1 Onboarding y perfilado (obligatorio, bloqueante)
El onboarding es un **agente conversacional + formulario progresivo**. Debe recoger y persistir:

- **Identidad fiscal:** razón social, CIF/VAT, país, dirección de envío y de facturación, régimen aduanero habitual.
- **Sector y actividad:** CNAE, qué compra, con qué frecuencia, estacionalidad.
- **Cuentas y accesos:** conexión a proveedores/marketplaces (OAuth cuando exista; credenciales cifradas
  cuando no), y **conexión financiera** (PSD2/agregador bancario o carga manual/CSV de extractos).
  Las credenciales de marketplace viven en un vault y nunca se exponen al LLM: el LLM solo recibe
  un `account_id` opaco y los agentes que navegan las usan desde el worker.
- **Presupuesto:** envelope por categoría y por operación, límite de crédito disponible, colchón de
  seguridad de tesorería (%), condiciones de pago preferidas (prepago / 30 / 60 / 90), divisa base.
- **Política de compra:** umbral de aprobación humana por importe, proveedores vetados, países excluidos,
  certificaciones exigidas (CE, ISO, REACH, FCC...), tolerancia a lead time, política de garantía.
- **Parámetros de negociación:** descuento objetivo por categoría, descuento máximo autorizado,
  agresividad (conservador / equilibrado / agresivo), tono (formal / cercano), idioma, si acepta
  contrapartidas (mayor volumen, prepago, plazo más largo) a cambio de precio.

**Reglas:** el onboarding nunca se da por completo si falta el encaje financiero; el sistema calcula un
**Buying Power Score** y un **Budget Envelope** y los muestra explícitamente. Toda decisión posterior
hereda esos límites.

## 3.2 Búsqueda y sourcing
- La empresa describe la necesidad en lenguaje natural ("necesito 5.000 botellas PET 500ml con tapón
  flip-top, entrega antes de junio"). Un agente la **normaliza a un `SourcingRequest` estructurado**:
  especificación, cantidades y escalones (MOQ), plazo, destino, certificaciones, presupuesto.
- El agente **planifica** qué fuentes consultar según categoría, geografía, plazo y presupuesto.
- Se lanzan **agentes de scraping especializados por plataforma** (Alibaba, AliExpress, Wallapop,
  Amazon Business, proveedores locales, catálogos propios). Cada uno devuelve resultados normalizados
  al mismo esquema `Offer`.
- Se deduplican ofertas del mismo vendedor/producto entre plataformas.
- Se enriquece cada oferta: ficha de vendedor, historial, rating, antigüedad, país, MOQ, escalado de
  precio por volumen, coste de envío, incoterm, plazo declarado, certificaciones declaradas.

## 3.3 Encaje financiero
Cada oferta se convierte a **landed cost** completo: precio unitario × cantidad + envío + seguro +
aranceles e IVA importación + coste de capital del plazo de pago + comisiones de pago + FX + riesgo
de divisa. Después se contrasta con:
- Presupuesto disponible del envelope.
- Tesorería proyectada a la fecha de pago.
- Límite de crédito.
- Colchón de seguridad mínimo.

El resultado es un veredicto explícito por oferta: **`within_budget` / `stretch` / `out_of_budget`**,
con la razón numérica. Una oferta `out_of_budget` nunca puede ser la recomendación nº1, aunque tenga el
precio más bajo.

## 3.4 Negociación autónoma (el núcleo)
Para las ofertas que pasan el filtro, un **agente negociador** entra en el chat del vendedor mediante
automatización de navegador (Puppeteer) y conduce una negociación por rondas.

**Estrategia (por defecto, configurable por perfil):**
1. Abrir conversación con contexto profesional: cantidad, plazo, destino, intención de compra recurrente.
2. Anclar bajo, justificado (no "quiero descuento", sino "con 5.000 uds. y prepago, ¿qué escalado aplica?").
3. Pedir **escalado de precios por volumen** antes de pedir descuento directo (suele dar más).
4. Contraofertar en escalera decreciente con incrementos decrecientes hasta el `target_discount`.
5. Usar contrapartidas autorizadas (mayor volumen, prepago, contrato marco, plazo más largo) solo si
   están habilitadas en el perfil.
6. Detectar señales de cierre ("te lo dejo en X si cierras hoy") y **nunca aceptar compromiso vinculante**
   sin aprobación humana: el agente negocia, no compra.
7. Cerrar con resumen escrito de la oferta final y pedir confirmación de condiciones por escrito.

**Guardarraíles duros:**
- Nunca superar `max_discount` ni comprometer volumen por encima de lo solicitado.
- Nunca aceptar prepago, garantías, plazos o penalizaciones sin autorización explícita del perfil.
- Máximo de rondas y de tokens por conversación; máximo de mensajes/hora por cuenta.
- Si el vendedor pide datos sensibles, pagos fuera de plataforma o contacto externo → escalar a humano.
- Si el vendedor propone un precio por debajo de un umbral de "sospechosamente barato" → marcar riesgo.
- Toda conversación se registra íntegra (transcripción + capturas) y es auditable.
- Un humano puede **tomar el control** del chat en cualquier momento; el agente se detiene limpiamente.

**Resultado:** un `NegotiationOutcome` con precio inicial, precio final, descuento logrado, contrapartidas
concedidas, condiciones, confianza y transcripción.

## 3.5 Valoración final y recomendación
Se puntúan todas las ofertas (originales y negociadas) con un modelo **MCDA (TOPSIS/Vikor-like)** de
pesos configurables por perfil:

```
score = w1·f(landed_cost) + w2·f(lead_time) + w3·f(vendor_reliability)
      + w4·f(financial_fit) + w5·f(margin_potential) + w6·f(spec_match)
      + w7·f(compliance_risk) + w8·f(negotiation_gain) − penalizaciones
```
- `w*` salen del perfil; `f()` normaliza cada criterio al rango [0,1] y es monótona y documentada.
- Restricciones duras (certificaciones, países vetados, presupuesto, MOQ) se aplican como **filtro previo**,
  no como penalización. Una oferta que no cumple se descarta con motivo visible.
- La salida debe ser **explicable**: para cada oferta, contribución de cada criterio al score y texto en
  lenguaje natural generado por el LLM a partir de esos números (nunca el LLM inventa el ranking).

La UI muestra: recomendación principal, 2 alternativas con trade-off explícito ("más barato pero +18 días
de plazo"), y el ahorro total conseguido vs. precio de lista.

## 3.6 Post-negociación
Bandeja de aprobaciones, exportación de la comparativa, generación de RFQ/orden de compra en PDF,
seguimiento de la compra, y memoria histórica: precios de referencia por producto y proveedor
(para usar en futuras negociaciones: "la última vez me lo dejaste en X").

---

# 4. ARQUITECTURA DE AGENTES

Orquestación en grafo (LangGraph) con estado persistido y reanudable. Agentes:

| Agente | Responsabilidad | Herramientas | Salida |
|---|---|---|---|
| `IntakeAgent` | Conversación de onboarding y normalización de necesidad | LLM structured output, validador de esquema | `CompanyProfile`, `SourcingRequest` |
| `PlannerAgent` | Decide fuentes, consultas, escalones de cantidad y presupuesto de la misión | LLM + reglas + catálogo de fuentes | `SourcingPlan` |
| `ScraperAgent` (× plataforma) | Extrae ofertas de una plataforma concreta | Puppeteer / Playwright, parsers, proxy rotativo | `Offer[]` |
| `EnrichmentAgent` | Ficha de vendedor, dedupe, normalización, traducción de especificaciones | LLM + scrapers auxiliares | `Offer` enriquecida |
| `FinanceAgent` | Landed cost, FX, encaje de tesorería, veredicto presupuestario | Motor de cálculo determinista (Python) + datos bancarios | `FinancialFit` |
| `NegotiatorAgent` | Conduce la conversación con el vendedor | Puppeteer (Node), playbook, guardarraíles | `NegotiationOutcome` |
| `EvaluatorAgent` | MCDA + explicación | Motor de scoring determinista + LLM para la narrativa | `RankedRecommendation` |
| `SupervisorAgent` | Control de calidad, detección de bloqueos, escalado a humano, control de coste | LLM + políticas | decisiones de flujo |

**Regla de oro arquitectónica:** todo lo que sea aritmética o decisión auditable (landed cost, scoring,
guardarraíles, límites) se implementa en **código determinista y testeado**; el LLM solo interpreta
lenguaje, planifica y redacta. El LLM no calcula precios ni decide si se puede pagar.

**Estados del grafo por oferta:** `discovered → enriched → financially_checked → negotiating →
negotiated → scored → recommended → awaiting_human → approved/rejected`. Todo cambio de estado se
persiste y es idempotente (una misión interrumpida se reanuda sin duplicar mensajes).

---

# 5. STACK DE DESARROLLO COMPLETO

## 5.1 Monorepo
- **pnpm workspaces + Turborepo** (monorepo híbrido TS/Python).
- Estructura:
  ```
  /apps
    /web            Next.js (frontend + BFF)
    /orchestrator   FastAPI + LangGraph (agentes, scoring, finanzas)
    /browser-worker Node/TS + Puppeteer (scraping y negociación)
  /packages
    /shared-types   esquemas Zod + generación de tipos Python (pydantic) desde contrato OpenAPI
    /ui             design system
    /eslint-config, /tsconfig
  /infra            Terraform / Docker Compose / Helm
  /docs             ADRs, runbooks, contratos de agentes
  ```
- Contratos entre servicios: **OpenAPI 3.1** como fuente de verdad; los tipos TS y los modelos Pydantic
  se generan desde ahí. Prohibido definir el mismo DTO dos veces a mano.

## 5.2 Frontend
- **Next.js 15 (App Router) + React 19 + TypeScript strict.**
- **Tailwind CSS v4 + shadcn/ui** (Radix) para el design system.
- **TanStack Query** (estado servidor) + **Zustand** (estado local de UI).
- **React Hook Form + Zod** para formularios y onboarding multi-paso.
- Streaming en tiempo real de la negociación: **SSE** desde el orquestador (transcripción del chat en vivo).
- **Recharts / Visx** para comparativas y desglose de landed cost. **TanStack Table** para la matriz de ofertas.
- **next-intl** (ES/EN/zh) desde el día uno.
- Auth de UI: **NextAuth/Auth.js** delegando en el IdP.
- **Storybook** + **Playwright** para E2E de los flujos críticos.

## 5.3 Orquestador de agentes (Python)
- **Python 3.12 + FastAPI + Pydantic v2.**
- **LangGraph** para el grafo de agentes (checkpointing con Postgres saver) y **LangChain** solo como capa
  de utilidades; el control de flujo es explícito, no delegado a `AgentExecutor`.
- **LiteLLM** como pasarela multi-modelo (permite cambiar de proveedor sin tocar código) con
  **router por coste/capacidad**: modelo grande para planificación y redacción, modelo pequeño para
  clasificación y extracción.
- Prompts versionados en el repo (`/prompts/*.jinja`) con evaluación automática (**promptfoo** o
  **DeepEval**) en CI; ningún prompt cambia sin pasar su suite de evaluación.
- **Celery** o **Arq** para tareas async de larga duración (con Redis).
- **pandas / numpy** para el motor financiero y el scoring; **pyxirr** para TIR/VAN si se evalúan compras
  de activos; **money/py-moneyed** para aritmética monetaria exacta (nunca floats para dinero).

## 5.4 Capa de navegador y scraping (Node/TS)
- **Node 22 LTS + TypeScript + Puppeteer** (con `puppeteer-extra` + stealth plugin) y **Playwright**
  como alternativa para plataformas donde sea más robusto.
- **Brokers de sesión:** `undici`/`got-scraping` para HTTP puro cuando no hace falta navegador (mucho más
  barato y rápido); Puppeteer solo cuando hay JS, login o chat.
- **Pool de navegadores** con Chromium headless en contenedores dedicados, `--no-sandbox` deshabilitado,
  límites de memoria, reciclado por número de páginas y watchdog.
- **Persistencia de sesión** por cuenta (cookies + storage state cifrados en vault) para no reloguear
  en cada misión, con detección de sesión invalidada y reautenticación asistida por humano.
- **Anti-bot:** rotación de proxies residenciales (**Bright Data / Oxylabs / IPRoyal**), gestión de
  fingerprint, límites de concurrencia por dominio, backoff exponencial, cola por dominio.
- **Parsers como plugins**: cada plataforma implementa una interfaz `PlatformAdapter` con
  `search()`, `getProduct()`, `getSeller()`, `openChat()`, `sendMessage()`, `readMessages()`.
  Añadir una plataforma = añadir un adapter + sus fixtures + sus tests. Nada más.
- **Cola de trabajos:** **BullMQ** sobre Redis, con prioridades, reintentos, DLQ y trazabilidad por misión.

## 5.5 Datos
- **PostgreSQL 16** como base transaccional (multi-tenant por `tenant_id` + RLS de Postgres).
- **Prisma** (desde `web`) y **SQLAlchemy 2 + Alembic** (desde `orchestrator`) sobre **el mismo esquema**;
  propiedad del esquema en un único paquete de migraciones para evitar deriva. Alternativa aceptada:
  Prisma como única herramienta si se genera cliente en ambos lados.
- **pgvector** para embeddings (productos, histórico de negociaciones, catálogos de proveedor → RAG).
- **Redis** para caché, colas, rate limiting y estado efímero de sesión de navegador.
- **S3-compatible (MinIO en local / R2 o S3 en prod)** para capturas de pantalla, PDFs, adjuntos de chat.
- **ClickHouse** (fase 2) para analítica de precios históricos y benchmarks de categoría.
- **dbt** para modelar los marts de precios y ahorro.

## 5.6 IA / LLM
- Modelos vía LiteLLM: un modelo frontier para `PlannerAgent`/`NegotiatorAgent`/narrativa y modelos
  pequeños/baratos para extracción, clasificación y traducción.
- **Embeddings** para búsqueda semántica de productos y recuperación de negociaciones previas.
- **Structured output obligatorio** (JSON Schema / tool calling) en toda salida que alimente código.
- **Trazabilidad de LLM:** **Langfuse** o **Phoenix/Arize** (self-hosted) para trazas, coste por misión,
  evaluación y datasets de regresión.
- **Evaluación continua:** golden set de misiones sintéticas (búsqueda, negociación, scoring) con métricas
  de precisión de extracción, calidad de negociación (descuento logrado, cumplimiento de guardarraíles)
  y fidelidad de la explicación.

## 5.7 Mensajería y tiempo real
- Colas: Redis/BullMQ (Node) + Redis/Celery (Python).
- Kafka o Redpanda **solo si** se necesita event sourcing entre servicios (fase 2). En MVP: Postgres
  `outbox` + Redis pub/sub.
- SSE/WebSockets para el streaming de la negociación al frontend.

## 5.8 Infraestructura y DevOps
- **Docker** para todo; **Docker Compose** para desarrollo local (Postgres, Redis, MinIO, Langfuse,
  Chromium).
- **Kubernetes (EKS/GKE)** en producción; los browser-workers en un **node pool dedicado** con más CPU/memoria.
- **Terraform** para IaC. **GitHub Actions** para CI/CD: lint, typecheck, tests, build, migraciones,
  escaneo de secretos y dependencias, deploy por entorno.
- **Observabilidad:** OpenTelemetry en todos los servicios → **Grafana + Loki + Tempo**, **Sentry** para
  errores. Dashboard específico de "salud del scraping": tasa de bloqueo por plataforma, CAPTCHAs,
  sesiones caídas, latencia de negociación, coste LLM por misión.
- **Gestión de secretos:** Vault o AWS Secrets Manager + **sops/age** para lo que esté en repo.
- **Feature flags** (Unleash/Flagsmith) para activar plataformas y estrategias de negociación.

## 5.9 Seguridad, privacidad y cumplimiento
- **Keycloak** (o Auth0/Clerk) como IdP: OIDC, MFA obligatorio, SSO empresarial, RBAC
  (`owner`, `admin`, `buyer`, `finance`, `viewer`).
- **Multi-tenancy estricta** con RLS; test automático que verifica aislamiento entre tenants.
- Cifrado en reposo (KMS) y en tránsito; credenciales de marketplace y datos bancarios cifrados con
  clave por tenant; nunca en logs, nunca en el contexto del LLM.
- **Audit log inmutable** de toda acción del agente (quién, qué herramienta, qué inputs, qué resultado).
- **GDPR**: base legal por tratamiento, minimización, retención configurable, export/borrado por titular.
- **Cumplimiento de plataformas**: revisar y documentar los ToS de cada marketplace; respetar `robots.txt`
  y rate limits; usar APIs oficiales cuando existan; el scraping se limita a lo estrictamente necesario
  para la finalidad y se documenta por plataforma en `/docs/compliance/<plataforma>.md`.
  El agente debe poder **desactivar una plataforma por flag** sin tocar código.
- **Anti-abuso propio:** rate limit por cuenta de vendedor, detección de duplicados, prohibición de
  contactar al mismo vendedor por múltiples misiones simultáneas.

## 5.10 Calidad
- **Vitest** (TS) y **Pytest** (Python); cobertura mínima 80% en módulos de dinero, scoring y guardarraíles.
- **Testcontainers** para Postgres/Redis en integración.
- **Playwright** E2E de los flujos: onboarding completo, misión de búsqueda, misión de negociación
  (contra un servidor de chat simulado), aprobación y recomendación.
- **Mocks de plataformas:** cada `PlatformAdapter` trae fixtures HTML/JSON grabados y un **servidor de
  chat simulado** para testear el negociador sin tocar plataformas reales. Esto es obligatorio: no se
  testea contra producción.
- **Contratos**: tests de contrato OpenAPI entre servicios; Pact opcional.
- **Load testing** (k6) sobre el orquestador y la cola de misiones.

---

# 6. MODELO DE DATOS (entidades mínimas)

```
Tenant, User, Role, Membership
CompanyProfile, CompanyFinancials (snapshot mensual), BudgetEnvelope
ConnectedAccount (platform | bank), CredentialRef (vault pointer)
UserProfilePreference (weights, negotiation params, hard constraints)
SourcingRequest, SourcingItem (spec, quantity tiers), SourcingPlan
Offer (platform, seller, unit_price, moq, tiers, shipping, incoterm, lead_time, currency)
Seller (rating, age, transactions, country, risk_flags)
FinancialFit (landed_cost breakdown, verdict, reasons)
Negotiation (offer_id, strategy, state, rounds, guardrail_hits)
NegotiationMessage (role: agent|seller|human, content, timestamp, screenshot_ref, redactions)
NegotiationOutcome (initial_price, final_price, discount_pct, concessions, terms, confidence)
Score, ScoreBreakdown (per criterion contribution)
Recommendation (rank, narrative, alternatives, savings)
Approval (requested_by, approver, decision, comment)
AuditEvent, LLMEvent (tokens, cost, model, prompt_version)
PriceHistory (product_key, seller, price, date) -> memoria de negociación
```

---

# 7. API (superficie mínima)

```
POST   /v1/onboarding/sessions            # conversación de perfilado
POST   /v1/companies/{id}/financials      # carga/oauth financiero
POST   /v1/sourcing-requests              # crea necesidad
POST   /v1/missions                      # lanza búsqueda+negociación
GET    /v1/missions/{id}                 # estado del grafo
GET    /v1/missions/{id}/events          # SSE: progreso y transcripción en vivo
GET    /v1/missions/{id}/offers          # ofertas normalizadas + veredicto financiero
POST   /v1/negotiations/{id}/takeover    # humano toma el control del chat
POST   /v1/negotiations/{id}/resume      # devuelve el control al agente
POST   /v1/negotiations/{id}/abort
GET    /v1/missions/{id}/recommendation  # ranking explicable
POST   /v1/approvals                     # aprobación humana de una oferta
POST   /v1/webhooks/platforms/{platform}
GET    /v1/audit                         # solo admin/compliance
```
Reglas: idempotency keys en todas las escrituras; paginación por cursor; errores RFC 9457
(problem+json); versionado por prefijo de ruta.

---

# 8. CRITERIOS DE ACEPTACIÓN (verificables, no aspiracionales)

1. Un usuario puede completar el onboarding y obtener un `BudgetEnvelope` y `BuyingPowerScore`
   persistidos y visibles, con validación de que no se puede lanzar una misión sin ellos.
2. Una `SourcingRequest` produce ≥3 ofertas normalizadas de ≥2 plataformas distintas en <5 minutos
   (en modo mock, <30 s en CI).
3. Todo `Offer` muestra un desglose de landed cost auditable, línea por línea, que cuadra con el total
   al céntimo (test property-based sobre la aritmética monetaria).
4. Una oferta `out_of_budget` jamás aparece como recomendación nº1 (test explícito).
5. El negociador nunca supera `max_discount` ni concede contrapartidas no autorizadas
   (suite de tests con vendedores adversariales: agresivos, evasivos, que piden pago externo,
   que ofrecen precios anómalamente bajos).
6. Toda negociación deja transcripción completa, estado final y `NegotiationOutcome`.
7. Un humano puede tomar el control y el agente se detiene sin enviar mensajes posteriores (test E2E).
8. Cambiar de perfil reordena el ranking y la UI explica por qué (test de consistencia del MCDA).
9. El coste LLM por misión es visible y está acotado por presupuesto configurable; al superarlo, la
   misión se degrada a modelo barato o se detiene con aviso.
10. Ningún secreto (credenciales de plataforma, datos bancarios) aparece en logs, trazas o contexto LLM
    (test de fuga de secretos en CI).
11. Aislamiento multi-tenant verificado por test automático.
12. Runbook documentado para: sesión de plataforma invalidada, CAPTCHA persistente, cambio de DOM en una
    plataforma (el adapter debe fallar de forma ruidosa y detectable, no silenciosa).

---

# 9. ROADMAP

**Fase 0 — Cimientos (2–3 semanas).** Monorepo, CI, auth, multi-tenant, esquema de datos, motor monetario,
observabilidad, contratos OpenAPI.

**Fase 1 — MVP honesto (6–8 semanas).** Onboarding + perfilado + `BudgetEnvelope`. Dos `PlatformAdapter`
con una plataforma vía API oficial siempre que exista y una vía scraping. `FinanceAgent` con landed cost.
`EvaluatorAgent` con MCDA y explicación. **Negociación en modo semi-automático** (agente redacta, humano
aprueba cada envío) contra el servidor de chat simulado. Sin pagos.

**Fase 2 — Negociación autónoma (6 semanas).** Envío autónomo con guardarraíles en una plataforma real,
takeover humano, memoria de precios, aprobaciones, RFQ en PDF. Tercera y cuarta plataforma.

**Fase 3 — Inteligencia (6 semanas).** Conexión financiera real (PSD2), proyección de tesorería,
margen potencial para revendedores, benchmarks de categoría, ClickHouse + dbt.

**Fase 4 — Escala.** Más plataformas como plugins, SSO empresarial, SLA, self-host de modelos pequeños
para extracción, marketplace interno de playbooks de negociación por categoría.

---

# 10. CÓMO DEBES TRABAJAR (reglas para ti, agente implementador)

- Antes de escribir código de una épica: escribe un **ADR** con las decisiones y un **plan de tareas**;
  espera validación si el plan toca dinero, guardarraíles o cumplimiento.
- Nada de lógica de negocio en componentes de UI ni en prompts. El prompt orquesta; el código decide.
- Toda función que toque dinero o límites lleva tests unitarios + property-based tests.
- Todo `PlatformAdapter` nuevo incluye: fixtures, tests, doc de compliance y flag de activación.
- No introduzcas dependencias pesadas sin justificarlo en el ADR.
- Si una plataforma no permite automatización conforme a sus términos, **no la implementes**: documenta
  el motivo y propón la alternativa (API oficial, acuerdo de partenariado, carga manual).
- Mantén el sistema ejecutable en local con `docker compose up` en menos de 10 minutos.
- Entrega siempre: código, tests, migraciones, actualización de docs y nota de riesgos.
