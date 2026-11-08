# Métricas de TRATO (catálogo)

Fuente de verdad de los nombres de métricas. Los dashboards de `infra/grafana/dashboards/` consultan
exactamente estos nombres. Si un lane cambia un nombre, cambia este documento y el dashboard en el mismo PR.

Cada métrica se emite con OpenTelemetry (OTLP → OTel Collector → Prometheus). En Prometheus aparece con el
nombre indicado en la columna **Prometheus** (ver _Traducción de nombres_ más abajo).

## Reglas de etiquetas

- Cardinalidad acotada. Solo se usan etiquetas de conjuntos cerrados o de catálogo: `platform` (id del
  registro de adaptadores), `band`, `role`, `endpoint` (id de configuración LLM), `outcome`, `cause`, etc.
- **Nunca** como etiqueta: importes, precios, saldos, tenant id, id de misión, id de oferta, nombre de
  vendedor, tokens de sesión, email. Esos datos van a trazas o a logs redactados, nunca a métricas.
- Los importes de coste del LLM por misión se miden con un histograma sin etiqueta de misión (ver `trato.mission.llm_cost`).
- Un valor fuera de su enum cerrado se emite como `other`, no como texto libre.

## Traducción de nombres (OTel → Prometheus)

`infra/otel/collector.yaml` usa el exportador `prometheus` con su configuración por defecto
(`add_metric_suffixes: true`). Por eso:

| Tipo OTel             | Unidad OTel                          | Nombre en Prometheus                           |
| --------------------- | ------------------------------------ | ---------------------------------------------- |
| Counter `trato.x.y`   | `{request}` (anotación entre llaves) | `trato_x_y_total`                              |
| Counter `trato.x.y`   | `s`                                  | `trato_x_y_seconds_total`                      |
| Histogram `trato.x.y` | `s`                                  | `trato_x_y_seconds_bucket` / `_sum` / `_count` |
| Histogram `trato.x.y` | `1` (ratio)                          | `trato_x_y_ratio_bucket` / `_sum` / `_count`   |
| Gauge `trato.x.y`     | `{item}`                             | `trato_x_y`                                    |
| Gauge `trato.x.y`     | `s`                                  | `trato_x_y_seconds`                            |

- Los puntos se convierten en guiones bajos. Las anotaciones `{...}` no añaden sufijo.
- Los atributos de recurso `service.name` llegan como `job`: `trato-orchestrator`, `trato-browser-worker`,
  `trato-web`. Los dashboards filtran por `job`.
- Los nombres de este catálogo son los nombres de Prometheus. Al crear un instrumento en código, usa el nombre
  OTel de la columna _OTel_ (con puntos y la unidad indicada).

## 1. Salud del scraping — DEV-5 (D5-10)

| OTel                                   | Prometheus                                   | Tipo      | Unidad      | Etiquetas                                                                                                                  | Emite         |
| -------------------------------------- | -------------------------------------------- | --------- | ----------- | -------------------------------------------------------------------------------------------------------------------------- | ------------- |
| `trato.scraping.requests`              | `trato_scraping_requests_total`              | Counter   | `{request}` | `platform`, `transport` (`http`\|`browser`), `outcome` (`ok`\|`error`\|`blocked`\|`captcha`\|`timeout`\|`session_invalid`) | D5-10         |
| `trato.scraping.request.duration`      | `trato_scraping_request_duration_seconds`    | Histogram | `s`         | `platform`, `transport`                                                                                                    | D5-10         |
| `trato.scraping.captchas`              | `trato_scraping_captchas_total`              | Counter   | `{captcha}` | `platform`                                                                                                                 | D5-10         |
| `trato.scraping.session.invalidations` | `trato_scraping_session_invalidations_total` | Counter   | `{session}` | `platform`                                                                                                                 | D5-10 (D5-02) |
| `trato.scraping.signals.missing`       | `trato_scraping_signals_missing_total`       | Counter   | `{signal}`  | `platform`, `signal` (`rating_count`\|`sales_count`\|`account_age`\|`reviews`\|`catalog`)                                  | D5-10         |
| `trato.scraping.queue.depth`           | `trato_scraping_queue_depth`                 | Gauge     | `{job}`     | `queue` (`scraping`\|`negotiation`)                                                                                        | D5-01         |

## 2. Calidad de precios — DEV-3 (motor), DEV-4 (D4-10, emisión)

| OTel                                    | Prometheus                                    | Tipo      | Unidad    | Etiquetas                                                                                   | Emite |
| --------------------------------------- | --------------------------------------------- | --------- | --------- | ------------------------------------------------------------------------------------------- | ----- |
| `trato.price_sanity.checks`             | `trato_price_sanity_checks_total`             | Counter   | `{check}` | `platform`, `band` (`within`\|`atypical`\|`implausible`\|`insufficient_reference`\|`other`) | D4-10 |
| `trato.price_sanity.relative_deviation` | `trato_price_sanity_relative_deviation_ratio` | Histogram | `1`       | `platform`                                                                                  | D4-10 |

`relative_deviation` es `|precio − mediana| / mediana` (sin importe absoluto).

## 3. Distribución de confianza del vendedor — DEV-3 (D3-06), DEV-4 (D4-10)

| OTel                                         | Prometheus                                         | Tipo      | Unidad         | Etiquetas                                                                                                         | Emite |
| -------------------------------------------- | -------------------------------------------------- | --------- | -------------- | ----------------------------------------------------------------------------------------------------------------- | ----- |
| `trato.seller_confidence.assessments`        | `trato_seller_confidence_assessments_total`        | Counter   | `{assessment}` | `platform`, `band` (`untrusted`\|`low`\|`medium`\|`high`\|`insufficient_data`)                                    | D4-10 |
| `trato.seller_confidence.manipulation_flags` | `trato_seller_confidence_manipulation_flags_total` | Counter   | `{flag}`       | `platform`, `flag` (`burst`\|`five_star_share`\|`low_verified_share`\|`duplicate_text`\|`account_creation_spike`) | D4-10 |
| `trato.seller_confidence.score`              | `trato_seller_confidence_score`                    | Histogram | `{score}`      | `platform` (buckets 0–100)                                                                                        | D4-10 |

El porcentaje `low` / `insufficient_data` se calcula en PromQL a partir de `assessments` (no se emite como gauge).

## 4. Salud del gate — DEV-4 (D4-11), DEV-2 (D2-09)

| OTel                              | Prometheus                           | Tipo    | Unidad       | Etiquetas                                                                       | Emite |
| --------------------------------- | ------------------------------------ | ------- | ------------ | ------------------------------------------------------------------------------- | ----- |
| `trato.gate.queue.depth`          | `trato_gate_queue_depth`             | Gauge   | `{item}`     | `cause` (causas de la §3.8 de la especificación)                                | D4-11 |
| `trato.gate.oldest_item.age`      | `trato_gate_oldest_item_age_seconds` | Gauge   | `s`          | `cause`                                                                         | D4-11 |
| `trato.gate.sla.missed`           | `trato_gate_sla_missed_total`        | Counter | `{item}`     | `cause`                                                                         | D4-11 |
| `trato.gate.items.resolved`       | `trato_gate_items_resolved_total`    | Counter | `{item}`     | `cause`, `action` (`follow`\|`renegotiate`\|`takeover`\|`hold`\|`discard`)      | D4-11 |
| `trato.signing.pending_decisions` | `trato_signing_pending_decisions`    | Gauge   | `{decision}` | `decision_type` (tipos cerrados de decisión)                                    | D2-09 |
| `trato.signing.decisions`         | `trato_signing_decisions_total`      | Counter | `{decision}` | `decision_type`, `outcome` (`signed`\|`rejected`\|`reauth_required`\|`invalid`) | D2-09 |

## 5. Salud del LLM — DEV-4 (D4-04, D4-05)

| OTel                         | Prometheus                           | Tipo      | Unidad      | Etiquetas                                                                                                    | Emite |
| ---------------------------- | ------------------------------------ | --------- | ----------- | ------------------------------------------------------------------------------------------------------------ | ----- |
| `trato.llm.requests`         | `trato_llm_requests_total`           | Counter   | `{request}` | `role`, `endpoint`, `outcome` (`ok`\|`error`\|`timeout`\|`circuit_open`\|`budget_exceeded`\|`schema_failed`) | D4-04 |
| `trato.llm.request.duration` | `trato_llm_request_duration_seconds` | Histogram | `s`         | `role`, `endpoint`                                                                                           | D4-04 |
| `trato.llm.json_repairs`     | `trato_llm_json_repairs_total`       | Counter   | `{repair}`  | `role`, `ladder_step` (`1`–`5`)                                                                              | D4-04 |
| `trato.llm.tokens`           | `trato_llm_tokens_total`             | Counter   | `{token}`   | `role`, `direction` (`input`\|`output`)                                                                      | D4-04 |
| `trato.llm.gpu_seconds`      | `trato_llm_gpu_seconds_total`        | Counter   | `s`         | `endpoint` (solo modelos autoalojados)                                                                       | D4-04 |
| `trato.llm.circuit.state`    | `trato_llm_circuit_state`            | Gauge     | `{state}`   | `endpoint` (0 cerrado, 1 semiabierto, 2 abierto)                                                             | D4-04 |
| `trato.mission.llm_cost`     | `trato_mission_llm_cost_usd`         | Histogram | `{usd}`     | (sin etiquetas) — una observación por misión al cerrarla                                                     | D4-04 |

Coste por misión = `sum(rate(trato_mission_llm_cost_usd_sum[1d])) / sum(rate(trato_mission_llm_cost_usd_count[1d]))`.

## Lo que existe hoy

`up` (scrape del colector y de Prometheus) y `prometheus_build_info` vienen de la configuración de Prometheus.
Los paneles basados en estas métricas se ven ya. El resto muestra «No data» hasta que el lane emita su métrica.
