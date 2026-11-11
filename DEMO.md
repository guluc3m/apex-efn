# DEMO — mercado simulado con IA en los dos lados

Guion para enseñar APEX-EFN en la hackathon **sin ninguna plataforma real, sin API de ningún modelo, sin
base de datos y sin Docker**. Todo corre en local y es determinista: el mismo botón da la misma conversación.

---

## 1. Qué se ve

Una página con tres cosas:

1. **El mercado** — catálogo falso (guantes de nitrilo, cajas de cartón) con precio, MOQ y proveedor.
2. **Los vendedores IA** — tres perfiles con su *persona* (el que aguanta, el chino, el nuevo sin historial).
3. **Los compradores IA** — tres compradores con presupuesto distinto que buscan, eligen proveedor, negocian
   por el hilo de mensajes y terminan en una de estas tres salidas:
   - `AGREED` → hay acuerdo y confirmación por escrito;
   - `ESCALATED` → el vendedor no baja del objetivo del comprador, así que el mejor precio va a la **cola humana**
     (es la regla del ticket #241);
   - `NO AGREEMENT` → nadie cede.

En la última ejecución:

| Comprador | Qué pasa |
|---|---|
| **Ana** (clínica, target 12%) | 3,68 → 3,81 € frente a 4,32 → 4,05 € del vendedor. No llega → **gate humano** con 4,05 € |
| **Bruno** (revendedor, target 2%) | 3,81 → 4,24 € frente a 4,32 → 4,24 € → **acuerdo a 4,24 €**, confirmación literal |
| **Chen** (importación, CNY) | 26,49 → 28,64 CNY frente a 30,80 → 28,64 CNY → **acuerdo**, confirmación en chino |

La conversación enseña lo importante del producto: **el vendedor no regala nada**, el comprador sube su escalera
ronda a ronda, y cuando no hay margen el sistema no inventa un acuerdo: lo manda a una persona.

---

## 2. Arrancarlo

Requisitos: Node 20+ con `pnpm`, y `uv` (Python 3.12+). Nada más.

```bash
./apps/orchestrator/src/apex/negotiation/sim/demo.sh
```

El script levanta los tres procesos, espera a que respondan y te deja la URL:

| Servicio | Puerto | Qué es |
|---|---|---|
| LLM stub | 8001 | Servidor falso compatible con OpenAI (`/v1/chat/completions`) |
| Mercado falso | 8002 | `apps/mock-marketplace` — plataformas `mock-a`, `mock-b` y `mock-c` |
| Interfaz | 8003 | La página de la simulación |

Abre **http://127.0.0.1:8003** y pulsa **Run scenario**. `Ctrl-C` en la terminal los para todos.

Si prefieres terminales separadas:

```bash
cd apps/llm-stub          && uv run python -m llm_stub                        # :8001
cd apps/mock-marketplace  && SIM_LLM_URL=http://127.0.0.1:8001 pnpm dev       # :8002
cd apps/orchestrator      && uv run python -m apex.negotiation.sim.server     # :8003
```

### Con un modelo de verdad (DeepSeek)

El demo funciona igual, pero las frases las escribe un modelo real. **Los precios los sigue decidiendo el
código**: si el modelo cambia una cifra, su frase se descarta y se usa la plantilla.

```bash
export SIM_LLM_URL=https://api.deepseek.com
export DEEPSEEK_API_KEY=sk-...            # o SIM_LLM_API_KEY
export SIM_LLM_MODEL=deepseek-chat        # opcional: es el valor por defecto con clave
export SIM_LLM_TIMEOUT_MS=8000            # opcional: una respuesta real tarda más que el stub
./apps/orchestrator/src/apex/negotiation/sim/demo.sh
```

**Dónde pongo la clave.** Dos formas, ninguna toca el repo:

```bash
# A) en la terminal, solo para esa sesión
export DEEPSEEK_API_KEY=sk-...

# B) en un .env.local en la raíz del repo (ya está en .gitignore), y el script lo carga solo
echo 'DEEPSEEK_API_KEY=sk-...' > .env.local
./apps/orchestrator/src/apex/negotiation/sim/demo.sh
```

No la pongas en `demo.sh`, en `compose.yaml` ni en ningún fichero versionado: `.env.local`, `.env` y
`.env.*.local` están ignorados por git, y el script no imprime la clave.

Con clave configurada el script **no arranca el stub** y apunta el mercado y el comprador al proveedor. Detalles:

- La clave viaja solo en la cabecera `Authorization`, nunca en el cuerpo ni en los logs.
- Sin clave, todo sigue siendo local y determinista (el escenario `sim-negotiation` del stub).
- Una partida son ~20–30 llamadas cortas (una por mensaje); con `deepseek-chat` es céntimos.
- El modelo no decide precios: el vendedor los calcula en `personas.ts` y el comprador en el playbook. El
  stub/proveedor solo pone el texto, y las guardas (`pinsPrice` en el vendedor, `plan_matches` en el
  comprador) tiran la frase si la cifra no coincide.

La conversación se genera **en directo**: al arrancar solo hay una frase por comprador, y cada pulsación pide
al modelo el siguiente mensaje. Con DeepSeek eso significa ~1–2 s por paso; con el stub, instantáneo.

Y si quieres la traza en texto en vez de la página:

```bash
cd apps/orchestrator
uv run python -m apex.negotiation.sim run --llm-url http://127.0.0.1:8001 --json /tmp/report.json
```

---

## 3. Guion de la demo (7 minutos)

1. **El problema (30 s).** Una pyme compra por volumen en marketplaces: comparar ofertas, comprobar al vendedor
   y regatear lleva horas y se hace a ojo. APEX-EFN lo automatiza **con un humano decidiendo el dinero**.
2. **El montaje (30 s).** "Esto no toca ninguna plataforma real": mercado falso en local, modelos falsos en local,
   datos sintéticos. Enseña la tabla de la sección 1.
3. **El catálogo (1 min).** Precios, MOQ y por qué el comprador elige un proveedor y no otro.
4. **La negociación (3 min).** Pulsa **Run scenario**: se abren los tres hilos y se pide al modelo solo la
   primera frase. A partir de ahí **cada Step es una llamada real al modelo** — verás el indicador de
   "pensando" y la respuesta llegar con su latencia. Cada tarjeta tiene su propio **Step / Play / All**, y los
   botones de la cabecera avanzan los tres chats a la vez (una ronda). Abre la tarjeta de **Ana** y ve
   leyendo la conversación:
   - el comprador abre bajo (3,68 €) y el vendedor **no acepta**: contesta 4,22 €;
   - cada ronda el vendedor cede un 15% de la diferencia, nunca su suelo;
   - Ana sube hasta su objetivo (3,81 €) y aun así el vendedor está en 4,05 €;
   - **no hay acuerdo**: la oferta va al gate. Ese es el punto: el sistema no decide solo sobre dinero.
   Después **Bruno**: mismo vendedor, objetivo más realista (2%), se encuentran en 4,24 € y el vendedor manda la
   **confirmación por escrito**.
5. **Quién escribe qué (1,5 min).** El texto lo pone un "modelo" (el stub), pero **ningún precio lo decide el
   modelo**: el playbook calcula cada número y el stub solo lo repite. Si el stub cambia una cifra, el motor
   descarta su frase y usa la plantilla. Enseñar `apps/llm-stub/scenarios/sim-negotiation.yaml`.
6. **Cierre (30 s).** Con un modelo real solo cambia `SIM_LLM_URL` a un vLLM/Ollama/llama.cpp compatible; los
   contratos, los guardarraíles y el gate no se tocan.

Frase para cerrar: *"el LLM escribe, el código decide, y una persona firma"*.

---

## 4. Qué es de mentira y qué no (dilo tú antes de que lo pregunten)

| Pieza | Realidad |
|---|---|
| Mercado | **Falso**: `apps/mock-marketplace`, datos sintéticos |
| Modelo | **Falso**: `apps/llm-stub`; para el demo, un escenario `echo_price` que repite el precio del prompt |
| Vendedores | **Deterministas**: máquina de estados en `personas.ts` (suelo, cesiones, cierres) |
| Compradores | **Reales**: el motor de negociación de verdad (playbook, guardarraíles, extracción, confirmación) |
| Base de datos | **Ninguna**: puertos en memoria |
| Docker | **Ninguno** |

Y la parte legal, en una frase: Wallapop y Vinted **prohíben** la automatización de su web (ADR-506 y
`docs/compliance/`), Alibaba y eBay están detrás de acuerdo de partner. Por eso `mock-c` imita la **forma de una
API autorizada** (búsqueda + hilos de mensajes, ADR-507): el adaptador que probamos aquí es el que se queda
cuando alguna plataforma diga que sí.

---

## 5. Cambiar el escenario

- **Compradores**: `DEFAULT_BUYERS` en `apps/orchestrator/src/apex/negotiation/sim/server.py` — cantidad, moneda,
  `target_discount_bp` (objetivo) y `max_discount_bp` (suelo). El objetivo decide el final: si queda por debajo
  del suelo del vendedor, verás un `ESCALATED`.
- **Vendedores**: `apps/mock-marketplace/fixtures/sellers.json` (`persona`, señales, reseñas). La persona `tough`
  es la que aguanta; `cooperative` acepta antes.
- **Catálogo**: `apps/mock-marketplace/fixtures/products.json`.
- **Puertos/URLs**: `SIM_MARKETPLACE_URL`, `SIM_LLM_URL`, `SIM_PORT`.

---

## 6. Si algo no arranca

| Síntoma | Causa |
|---|---|
| "The scenario could not run" y el mercado no responde | El mercado no está en 8002 (`pnpm dev` en `apps/mock-marketplace`) |
| El vendedor responde frases raras o genéricas | El stub no está, o `SIM_LLM_URL` está vacío: sigue funcionando con las plantillas |
| `EADDRINUSE` | Quedó un proceso de una ejecución anterior: `ss -lptn 'sport = :8002'` y mátalo |
| `no Python executable was found` | `.venv` vacío tras un disco lleno: `uv sync` en `apps/orchestrator` y `apps/llm-stub` |

---

## 7. Dónde está el código

```
apps/mock-marketplace/src/platforms/mock-c.ts      la plataforma API-first y sus hilos
apps/mock-marketplace/src/chat/personas.ts         los vendedores IA (suelo, cesiones, personas)
apps/mock-marketplace/src/chat/phraser.ts          reescritura por el stub, con guarda de precio
apps/llm-stub/scenarios/sim-negotiation.yaml       el "modelo" del demo
apps/orchestrator/src/apex/negotiation/sim/        compradores IA, pipeline, CLI, página y demo.sh
```

Decisiones: `docs/adr/505-mock-b-html-over-http.md`, `506-wallapop-not-automated.md`,
`507-mock-c-sanctioned-api-shape.md`.
