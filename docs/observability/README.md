# Observabilidad de TRATO

Guía corta. El catálogo de métricas está en [`metrics.md`](./metrics.md). Los dashboards están en
`infra/grafana/dashboards/` y se cargan solos en Grafana (`http://localhost:3002`, usuario `admin`).

## Cómo se envía la telemetría

| App                         | Trazas y métricas                         | Logs                           | Errores                    |
| --------------------------- | ----------------------------------------- | ------------------------------ | -------------------------- |
| Orchestrator (Python)       | OTLP/HTTP → colector → Tempo / Prometheus | OTLP → Loki (y JSON en stdout) | Sentry si hay `SENTRY_DSN` |
| Browser worker (Node)       | OTLP/HTTP → colector → Tempo / Prometheus | pino JSON en stdout            | Sentry si hay `SENTRY_DSN` |
| Web (Next.js, runtime Node) | OTLP/HTTP (`@vercel/otel`, `trato-web`)   | —                              | Sentry si hay `SENTRY_DSN` |

Variables de entorno (estándar OTel donde existe):

- `OTEL_EXPORTER_OTLP_ENDPOINT`: base del colector. Por defecto `http://localhost:4318`.
- `OTEL_SDK_DISABLED=true`: apaga exportadores. Los logs siguen redactados y salen por stdout.
- `OTEL_RESOURCE_ATTRIBUTES=deployment.environment=<entorno>`: etiqueta de entorno (el worker la lee de aquí).
- `TRATO_ENVIRONMENT`, `TRATO_LOG_LEVEL`.
- `SENTRY_DSN`, `SENTRY_TRACES_SAMPLE_RATE` (por defecto `0`). Sentry se desactiva si no hay DSN.

El exportador nunca bloquea el arranque. Si el colector no responde, los lotes se reintentan en segundo plano.
Un `flush` o `shutdown` sí puede esperar al tiempo de espera del exportador mientras el colector está caído.

## Cómo ver la telemetría

1. `pnpm dev:up` (levanta el stack con el colector, Prometheus, Loki, Tempo y Grafana).
2. Grafana → carpeta **TRATO**: cinco dashboards (scraping, calidad de precios, confianza de vendedores,
   gate y LLM). Cada uno tiene un panel sobre `up{job="otel-collector"}` que ya funciona. El resto muestra
   «No data» hasta que el lane correspondiente emita sus métricas.
3. Trazas: Grafana → Explore → Tempo. Logs: Explore → Loki con `{service_name="trato-orchestrator"}`.

## Contrato de redacción

La redacción se aplica **antes** de que un dato salga del proceso: en logs, en atributos y eventos de span
(al exportar), y en los eventos de Sentry. Las reglas están implementadas dos veces, con el mismo
comportamiento, y las dos suites comparten [`redaction-vectors.json`](./redaction-vectors.json):

- Python: `apps/orchestrator/src/trato/platform/redaction.py`
- TypeScript: `packages/redaction/src/redaction.ts` (lo reutilizan el worker y la web)

### Reglas por clave

Una clave es sensible si, tras partirla en palabras (separadores y cambios de mayúscula), contiene:

- una palabra o frase sensible: `password`, `passwd`, `secret`, `credential(s)`, `authorization`, `cookie(s)`,
  `apikey`, `api_key`, `private_key`, `session_state`, `iban`, `bank_account`, `buying_power`, `budget`, `envelope`;
- `token` sin modificador permitido (`token_count`, `tokens`, `token_type`, `max_tokens` **no** son sensibles);
- `signature` sin modificador permitido (`signature_status`, `signature_hash`, `signature_id` **no** son sensibles);
- `minor` o `bp` (importes en unidades menores o en puntos básicos);
- un nombre de métrica financiera de la especificación §3.1.1 (`cash_balance`, `credit_line_limit`,
  `revenue`, `safety_buffer_pct`, `payment_term_days`, …).

El valor de una clave sensible se sustituye entero por `[REDACTED]`, aunque sea `null`.

### Reglas por valor

Dentro de cualquier cadena se sustituyen: cabeceras `Authorization`/`Cookie` completas, `Bearer <token>`,
JWT, tokens de Vault (`hvs.`, `hvb.`, `hvr.`, `s.`+24), claves `AGE-SECRET-KEY-1…`, bloques PEM de clave privada,
claves tipo `sk-…`, IBAN, credenciales en URL (`scheme://usuario:clave@`) y los pares `clave=valor` o `clave: valor`
con una palabra sensible o una métrica financiera.

### Garantías

- Nunca lanza excepciones. Si algo falla, el valor se sustituye por `[REDACTED]` y se incrementa un contador de errores.
- Profundidad máxima 32. Por encima, la rama se sustituye entera.
- Sentry: `send_default_pii=false`, `include_local_variables=false`, y `before_send` / `before_send_transaction`
  pasan el evento completo por el redactor.

### Qué no hacer

- No pongas importes, saldos, IBAN, tenant id ni secretos como etiquetas de métrica.
- No metas datos sensibles en el nombre de un span ni en el mensaje de un log con formato libre si puedes usar
  un campo. Los campos siempre se redactan; el texto libre solo cuando coincide con un patrón.
- Si necesitas un campo nuevo que contenga la palabra `token` o `signature` y no es secreto, usa un nombre
  con un modificador permitido (`_count`, `_status`, `_hash`…) o amplía las listas en **los dos** lenguajes y en
  `redaction-vectors.json` en el mismo PR.

## Cómo añadir una métrica

1. Añade la fila en [`metrics.md`](./metrics.md): nombre OTel, nombre Prometheus, tipo, unidad, etiquetas y quién la emite.
   Las etiquetas deben ser conjuntos cerrados.
2. Emite el instrumento con el nombre OTel (con puntos) y la unidad de la tabla.
   Python: `metrics.get_meter("trato").create_counter(...)`. TypeScript: `metrics.getMeter(...)`.
3. Si el dashboard debe mostrarla, añade el panel en `infra/grafana/dashboards/*.json`.
   Los paneles de Prometheus solo pueden referirse a métricas del catálogo o a métricas que existan hoy.
4. Comprueba que el panel renderiza con datos locales (`pnpm dev:up` y un script de prueba).

## Verificación

- Python: `cd apps/orchestrator && uv run pytest -q tests/platform` (incluye la prueba de fuga, criterio 29).
- TypeScript: `pnpm --filter @trato/browser-worker exec vitest run` y `pnpm --filter @trato/redaction test`.
- Los vectores son la fuente de verdad. Si cambias una regla, cambia primero el vector.
