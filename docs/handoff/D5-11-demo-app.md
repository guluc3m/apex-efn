# Handoff — demo de la app completa (D5-11)

Estado a 2026-11-11, rama `dev5/D5-11-demo-handoff`, PR **#415** (`dev5/D5-11-sim-brand`).
Esto es lo que funciona, lo que no, cómo comprobarlo y qué haría a continuación. Léelo antes de tocar nada.

## Objetivo

Que la demo del hackathon se pueda presentar **desde la app** (`apps/web`), no solo desde la página de
simulación: una misión creada en la web descubre ofertas del mercado falso, puntúa la confianza del
vendedor, comprueba el encaje financiero, negocia en el chat del vendedor y acaba en el gate para que un
humano decida.

## Cómo arrancar

```bash
pnpm demo:app        # compose + rol de BD + flags de Unleash + 4 procesos; Ctrl-C para todo
pnpm demo:app:stop   # si quedó algo colgado
```

- Web: <http://localhost:3000/es> · `owner-a@apex.local` / `apex-dev` (la primera vez pide configurar el
  autenticador; el TOTP viejo se borró, se enrola con el QR).
- Orquestador: `:8000` · marketplace `:8002` · worker `:4010` · llm-stub `:8001`.
- Logs: `/tmp/apex-demo/*.log`.
- Modelo real opcional: `DEEPSEEK_API_KEY` en `.env.local` (raíz, gitignored) o en el entorno. El banner
  dice qué modelo usa. Sin clave, todo va contra el stub.

## Lo que está verificado (con `mock-a`)

Misión con *«Necesito 5000 guantes de nitrilo para nuestro almacén de Madrid»*, país ES:

- 7 ofertas descubiertas por el camino real (orquestador → worker → adaptador → marketplace).
- Confianza por vendedor: 92, 83, 47, 35 e `insufficient_data`.
- Encaje financiero `within_budget` con landed cost por oferta.
- 4 negociaciones abiertas con transcripción real (agente/vendedor), 2 cerradas y 2 escaladas.
- 3 ofertas en el gate con causa y SLA; misión en `awaiting_decision`.
- `GET /v1/dashboard/deals` devuelve la forma del contrato (`items`, `offer` anidada, `actions`), con
  sanity, confianza y landed cost completos. La web pinta banda, mediana, muestra, desglose de coste y
  «por qué esta confianza».

Tests: `tests/api tests/agents tests/domain tests/negotiation` → 1082 en verde; `contracts:check` al día;
`pnpm --filter @apex/web typecheck` limpio; 80 tests del mock-marketplace.

## Lo que NO está verificado / está roto

1. **Nadie ha completado una misión de punta a punta después del último arreglo.** El último commit
   (`0873a72`, `2d11675`) cambia el runner (misión sin ofertas → falla con `no_offers_found`), el mapeo de
   estado (`awaiting_decision` en vez de `sourcing`) y añade productos ESP32 al catálogo. Los tests pasan,
   pero falta una ejecución real con `pnpm demo:app` + una misión.
2. **El planificador puede pedir categorías que el catálogo no tiene.** `catalog.search()` exige que
   *todos* los tokens coincidan. Si la búsqueda no encuentra nada, ahora la misión falla con
   `no_offers_found` (antes se quedaba en `sourcing` para siempre). Para la demo: guantes de nitrilo o
   placas ESP32-S3 (añadidas a propósito).
3. **DeepSeek no se ha probado con una clave real.** El cableado existe (`LLM_GATEWAY_API_KEY`,
   `LLM_GATEWAY_URL`, `LLM_MODEL_OVERRIDE`, capacidad `json_object` declarada, clave por referencia). Falta
   ejecutar con clave y comprobar que la salida estructurada del intérprete valida.
4. **El rol `embedder` también apunta al endpoint configurado.** DeepSeek no tiene embeddings; hoy nada en
   la demo lo llama, pero si se llama, revienta.
5. **Nada está firmado.** `signature_status` es siempre `pending`/`unsigned`; las acciones del trato abren
   decisión y devuelven `428 reauth_required`. El snapshot financiero de la demo se activa **sin firma**
   (`activation_decision_id = "demo:unsigned"`, solo con `DEMO_MODE=1`, logueado).
6. **`band_lower` / `band_upper` no los produce el motor de sanity (D3-07).** El gráfico dibujará la banda
   en cuanto existan; hoy pinta mediana y pie con muestra/dispersión.
7. **La prosa de la negociación se repite** con el stub (el modelo solo escribe texto; los precios los
   decide el código). Con DeepSeek varía.

## Mapa de ficheros tocados

| Área | Ficheros |
|---|---|
| Ingesta de señales y ofertas | `apex/agents/scraping.py`, `apex/agents/browser_worker.py`, `apex/agents/trust_port.py`, `apex/agents/ports.py` |
| Runner y estado | `apex/agents/mission_runner.py`, `apex/api/missions.py`, `apex/api/contract_map.py` |
| Datos del motor en la API | `apex/agents/{sanity_port,finance_port}.py`, `apex/api/contract_map.py` |
| Demo | `apps/orchestrator/src/apex/wiring.py` (`seed_demo_financials`, ECB), `apex/agents/onboarding.py` (`activate_unsigned_for_demo`), `apex/config.py` (`demo_mode`, `mock_marketplace_url`, `negotiation_*`) |
| LLM real | `apex/wiring.py` (`DefaultRoleConfigProvider`), `apex/config.py` (`llm_model_override`) |
| Worker | `apps/browser-worker/src/jobs/bull.ts` (un worker por plataforma registrada) |
| Web | `apps/web/src/components/{decisions,compare}/**`, mensajes i18n |
| Infra | `infra/scripts/demo-app.sh`, `package.json`, `DEMO.md` |
| Fixtures | `apps/mock-marketplace/fixtures/products.json` (2 referencias ESP32-S3) |

## Siguientes pasos, por prioridad

1. **Ejecutar la demo entera con `mock-a`** y confirmar que la misión llega a `awaiting_decision` y que el
   embudo avanza de fase. Si falla, el motivo ya aparece en la misión (`runner_crashed:` / `no_offers_found`).
2. **Probar con `DEEPSEEK_API_KEY`**: dos peticiones distintas deben producir especificaciones distintas
   (antes el stub devolvía siempre lo mismo). Revisar `llm.roles.*` y el rol `embedder`.
3. **Plataformas reales**: el puente de negociación de `main` va por el chat del browser worker; `mock-b`
   no negocia (transporte `browser` desactivado). Si se quiere negociar en `mock-b`, mirar
   `NEGOTIABLE_PLATFORMS` en `apex/wiring.py`.
4. **`band_lower`/`band_upper`** en el motor de sanity (D3-07) para que el gráfico pinte la banda.
5. **Firma**: cablear el flujo de `signing-sessions` en las acciones del trato (D6-03/D2-09).

## Reglas para quien siga

- Un carril por persona; no editar ficheros de otro carril (ver `AGENTS.md` §2).
- No arrancar el stack en CI: `pnpm demo:app` es solo local. `ci:local` sigue siendo la puerta de merge.
- Las claves nunca al repo: `.env.local` (raíz) o entorno.
- Nada de umbrales de negocio en código: `config/defaults/` + BD.
