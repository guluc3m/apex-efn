# Notas del Tech Lead (no forman parte del prompt)

Documento de revisión humana. Los ADRs que genere el agente implementador deben contrastarse contra
estas decisiones antes de aceptarse.

---

## Decisiones tomadas (y por qué)

### 1. El agente negocia, no compra
Sin aprobación humana explícita no hay compromiso vinculante. Consecuencia de diseño: estado
`awaiting_human` obligatorio, dashboard de decisión y endpoint de aprobaciones. El humano no es cuello de
botella en todo, solo en lo que el sistema no puede juzgar (banda anómala, vendedor poco fiable,
presupuesto, importes altos).

### 2. Puppeteer solo donde hace falta
Reservar el navegador para login y chat ahorra del orden del 70% del coste operativo. El `PlatformAdapter`
declara `transport: http | browser` y el `PlannerAgent` lo respeta.

### 3. MCDA determinista, LLM solo narra
Si el ranking lo produce el LLM no es defendible ante un CFO ni reproducible en auditoría.

### 4. El control de precios anómalos va antes de negociar
Dos razones: economiza (no se negocia con un fraude) y protege al humano (no le llega ruido a la cola).
La estadística es **mediana + MAD**, no media + desviación típica, porque los outliers son precisamente el
objeto de estudio. Bandas asimétricas: el lado barato es más peligroso que el caro.

### 5. Firmas Ed25519 con clave privada en el dispositivo
Alternativa descartada: firma en servidor con clave custodiada. Es más simple pero no prueba *quién*
decidió, solo *que el sistema registró algo*. Con clave no exportable en cliente + step-up auth, la firma
es no repudiable en la práctica y el servidor no custodia material sensible.

### 6. La sesión de firma de 15 minutos es un compromiso explícito (nuevo)
Firmar cada decisión con passkey es correcto y, con 40 tratos en cola, se vuelve insufrible. Si el equipo
empieza a evitar el dashboard por fricción, la seguridad se convierte en teatro y el resultado es peor que
no tenerla. Por eso: **una autenticación abre una ventana de 15 minutos, no deslizante**, y dentro de ella
las firmas se enlazan al `signing_session_id` y al instante de autenticación. Salvaguardas para que esto no
sea un bypass: caducidad fija (no se renueva al firmar, si no nunca expiraría), máximo de decisiones por
sesión, reautenticación inmediata por importe alto y para operaciones estructurales (activar snapshot
financiero, cambiar umbrales, tocar claves), e invalidación ante cambio de dispositivo o de red. En
auditoría queda registrado el momento exacto de la autenticación, así que "firmó dentro de la ventana" es
verificable, no una suposición.

### 7. Confianza del vendedor como ciudadano de primera clase (nuevo)
Es el `SellerRisk` que faltaba. Cuatro decisiones de diseño que merecen defenderse:

- **Suavizado bayesiano del rating**: sin shrinkage, un vendedor con una reseña de 5,0 puntúa por encima de
  uno con 500 reseñas a 4,8, y el sistema recomendaría comprar a desconocidos. Con prior de 25 y media de
  categoría, el vendedor nuevo converge a la media hasta acumular evidencia.
- **La confianza acota, no suma**: no se compensa un vendedor dudoso con un precio bueno. Si la confianza es
  baja, hay gate humano aunque el precio sea normal. Y si el precio es anómalamente barato **y** el vendedor
  es de baja confianza, se sube un nivel de severidad (de `normal` a `atypical`, de `atypical` a
  `implausible`). Es la señal de fraude más informativa que existe y sumarla en una media la diluiría.
- **Detección de manipulación de reseñas**: ráfagas anómalas, proporción enfermiza de 5 estrellas, reseñas
  no verificadas y textos clonados no bajan el score: **lo capan**. Un vendedor que infla sus reseñas no
  debe poder compensarlo con volumen.
- **El snapshot entra en el payload firmado**: la decisión se firma con el score y el `model_version` que el
  responsable tenía delante. Si mañana cambia el modelo, se puede demostrar qué se sabía al decidir.

### 8. CSV como fuente financiera en lugar de PSD2
PSD2 exige licencia, contratos con agregadores y meses de integración. El CSV desbloquea el MVP y define el
contrato de datos. Riesgo real: **el CSV caduca**, de ahí `finance.stale_after_days`.

### 9. Gateway LLM compatible OpenAI
Requisito de autoalojamiento y de no quedar atados a un proveedor. La abstracción es HTTP, no un SDK.
Consecuencia: capacidades declaradas por endpoint y escalera de structured output, porque no se puede
asumir `json_schema` en un modelo pequeño servido con llama.cpp.

### 10. Solo EUR, USD y CNY
Enum cerrado en base de datos. Reduce FX a una matriz 3x3 con pivote EUR y hace testeable la aritmética.

---

## Decisiones que dejé abiertas (el prompt obliga a preguntar)

- Valores por defecto de `sanity.z_ok`, `z_gate`, `floor_per_unit` y `ceiling_per_unit` **por categoría**:
  los números del documento son puntos de partida, no calibrados con datos.
- Pesos exactos de las señales de confianza del vendedor y umbrales de banda: también a calibrar.
- Si `insufficient_reference` debe bloquear o permitir negociar con aviso (hoy: bloquea).
- Importes para `approval.threshold`, `approval.dual_control_above` y `signing.high_value_reauth_above`.
- Si el escrow de claves se ofrece o no (hoy: opcional y desactivado).

---

## Riesgos abiertos

### Los datos de reputación los controla la plataforma
Antigüedad, ventas, catálogo y reseñas son lo que el marketplace **dice** que es el vendedor. Un vendedor
con identidad verificada por terceros (KYC, escrow, seguro de la plataforma) vale más que uno con 4.000
ventas. Conviene ponderar señales de garantía institucional por encima de las de volumen, y dejar de tratar
el rating como la señal principal.

### Sesgo contra vendedores nuevos
El suavizado bayesiano penaliza sistemáticamente al que empieza, y un vendedor nuevo con buenas métricas
puede ser mejor compra que uno viejo y mediocre. Con banda `insufficient_data` el sistema manda a gate: hay
que decidir si eso es política aceptable o si se traduce en pérdida de oportunidades. Recomendación: que el
gate muestre explícitamente "vendedor nuevo, sin historial suficiente" para que la decisión sea consciente.

### Identidad del vendedor entre plataformas
El mismo vendedor puede operar en dos marketplaces con métricas distintas. Sin resolución de identidad, la
confianza no es transferible y el histórico se fragmenta. No está resuelto y no es trivial.

### ToS y bloqueos
Wallapop y Alibaba son hostiles a la automatización. Cada plataforma necesita su
`/docs/compliance/<plataforma>.md`. El sistema debe poder apagar una plataforma por flag.

### Calidad del chat
Multilingüe (chino incluido), respuestas truncas, emojis, audio, cambio de canal. Los tests adversariales
del criterio 10 son el corazón del producto: si esa suite no existe, el producto no está terminado.

### Aritmética monetaria y FX
Nunca floats. El riesgo real es la **tasa del día de pago** frente a la del día de la oferta: una compra a
90 días en CNY puede moverse más que el descuento negociado. Conviene un aviso explícito de exposición FX
en el dashboard.

### Coste LLM
El presupuesto por misión es un límite duro en el grafo, no una métrica pasiva. Con modelos autoalojados el
coste es GPU-segundo: medirlo igual.

---

## Preguntas pendientes de negocio

1. ¿Qué descuento máximo autorizado por categoría? Sin esto el negociador no puede operar.
2. ¿Se aceptan contrapartidas (prepago, contrato marco) en el MVP o solo en fase 2?
3. ¿La orden de compra la emite APEX-EFN o se exporta para el ERP del cliente?
4. ¿Hay un responsable de cumplimiento que firme los docs de ToS por plataforma?
5. RESUELTO: fuente de datos financieros = CSV en el onboarding.
6. RESUELTO: divisas soportadas = EUR, USD, CNY.
7. RESUELTO: fricción de firma = sesión de 15 minutos no deslizante con reautenticación por importe.
8. ¿Cuál es la política con vendedores nuevos: gate sistemático o umbral de confianza más laxo a cambio de
   descuento esperado?
9. ¿Se exige identidad verificada por la plataforma (KYC/escrow) como requisito duro para comprar?

