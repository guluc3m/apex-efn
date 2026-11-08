# Notas del Tech Lead (no forman parte del prompt)

Documento de revisión humana. Los ADRs que genere el agente implementador deben contrastarse contra
estas decisiones antes de aceptarse.

---

## Decisiones tomadas (y por qué)

### 1. El agente negocia, no compra
Sin aprobación humana explícita no hay compromiso vinculante. Un LLM enviando mensajes a vendedores
reales en nombre de la empresa no puede tener capacidad de cierre. Consecuencia de diseño: existe un
estado `awaiting_human` obligatorio y un endpoint `POST /v1/approvals`.

### 2. Puppeteer solo donde hace falta
Muchas plataformas permiten HTTP directo o disponen de API (Amazon SP-API, catálogos de proveedor,
RSS de distribuidores). Reservar el navegador para login y chat ahorra del orden del 70% del coste
operativo y reduce superficie de bloqueo. Consecuencia: el `PlatformAdapter` declara su `transport`
(`http` | `browser`) y el `PlannerAgent` lo respeta.

### 3. MCDA determinista, LLM solo narra
Si el ranking lo produce el LLM no es defendible ante un CFO ni reproducible en auditoría. El scoring
es una función pura, testeada, con pesos explícitos y contribuciones por criterio expuestas en la UI.
El LLM recibe `ScoreBreakdown` ya calculado y redacta la explicación.

### 4. Stack híbrido TS + Python
Python para orquestación de agentes, motor financiero, scoring y analítica (mejor ecosistema de datos
y de grafos de agentes). Node/TS para Puppeteer, frontend y workers de navegador (Puppeteer es
nativo y el control de browser es más robusto). Coste: dos runtimes y deriva de esquema entre Prisma
y SQLAlchemy — mitigado con OpenAPI como fuente de verdad y un único paquete de migraciones.

### 5. Negociación semi-automática en Fase 1
La autonomía total en plataformas hostiles a la automatización es un riesgo técnico y legal simultáneo.
La Fase 1 (agente redacta, humano aprueba cada envío) permite medir viabilidad real antes de invertir
en autonomía. Es una decisión de gestión de riesgo, no una limitación técnica.

---

## Riesgos abiertos

### ToS y bloqueos
Wallapop y Alibaba son hostiles a la automatización. Cada plataforma necesita su
`/docs/compliance/<plataforma>.md` con la cláusula aplicable, la decisión tomada y la alternativa si se
desactiva. El sistema debe poder apagar una plataforma por feature flag sin tocar código.

### Fraude y verificación de identidad del vendedor
Pagos fuera de plataforma, precios anómalamente bajos, vendedores recién creados, suplantación. Merece
un módulo de riesgo propio (`SellerRisk`), no solo un flag. Umbral de "sospechosamente barato" a definir
por categoría con el equipo de compras.

### Calidad del chat
El negociador debe manejar multilingüe (chino incluido), respuestas truncas, emojis, audio, y vendedores
que cambian de canal. Los tests adversariales del criterio de aceptación 5 son el corazón del producto:
si esa suite no existe, el producto no está terminado.

### Aritmética monetaria
Nunca floats para dinero. Aritmética decimal exacta, FX con fecha y fuente registradas, redondeo
documentado por divisa. Test property-based obligatorio.

### Coste LLM
Una misión con 40 ofertas y negociación puede ser cara. El presupuesto LLM por misión es un límite duro
en el grafo, no una métrica pasiva.

---

## Preguntas pendientes de negocio

1. ¿Qué descuento máximo autorizado por categoría? Sin esto el negociador no puede operar.
2. ¿Se aceptan contrapartidas (prepago, contrato marco) en el MVP o solo en Fase 2?
3. ¿Fuente de datos financieros: PSD2 desde el inicio o CSV manual en el MVP?
4. ¿La orden de compra la emite TRATO o se exporta para el ERP del cliente?
5. ¿Mercado inicial y divisas soportadas?
6. ¿Hay un responsable de cumplimiento que firme los docs de ToS por plataforma?
