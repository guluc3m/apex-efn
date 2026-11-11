// APEX-EFN — corte estático de 12 diapositivas para 7 minutos.
// Compilar desde esta carpeta:
//   typst compile --root ../.. --font-path fuentes presentacion-7min.typ presentacion-7min.pdf
// Sin animaciones: cada diapositiva es una página del PDF.
#import "@preview/touying:0.6.1": *
#import themes.default: slide
#import "tema.typ": *

#set document(title: "APEX-EFN · 7 minutos")
#let margen = 56pt
#show: touying-slides.with(
  config-common(slide-fn: slide),
  config-page(
    width: 1280pt, height: 720pt,
    fill: c.bg,
    margin: (x: margen, top: 104pt, bottom: 36pt),
    header-ascent: 0pt,
    footer: none,
    header: {
      place(top + left, dy: 72pt, rect(
        width: 1280pt, height: 1pt,
        fill: gradient.linear((c.accent-line, 0%), (c.line, 70%), (c.line, 100%)),
      ))
      place(top + left, dx: margen, dy: 23pt, logo(40pt))
      place(top + right, dx: -margen, dy: 26pt, context text(font: fuente, size: 19pt, fill: c.muted, number-width: "tabular")[
        #utils.slide-counter.display() / #utils.last-slide-number
      ])
    },
  ),
)
#set text(font: fuente, fill: c.ink, size: 24pt, lang: "es", number-width: "tabular")
#set par(leading: 0.55em)
#set block(spacing: 0pt)

#let sin-marco = config-page(margin: 0pt, header: none)
#let titulo(t) = block(below: 26pt, text(size: 44pt, weight: 600, tracking: -0.02em, t))
#let suave(t, tam: 22pt) = text(size: tam, fill: c.soft, t)
#let peq(t) = text(size: 17pt, fill: c.muted, t)
#let regla = line(length: 100%, stroke: 1pt + c.line)
// Pie de tiempo: siempre abajo a la derecha, fuera del área de contenido.
#let pie(t) = place(bottom + right, dy: 15pt, text(size: 17pt, fill: c.muted, number-width: "tabular")[#t])
#let kicker(t) = text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em, upper(t))
#let flecha = text(fill: c.control, size: 18pt)[→]

// 1 ─ Portada ───────────────────────────────────────────────────────
#slide(config: sin-marco)[
  #grid(
    columns: (700pt, 1fr), rows: 720pt,
    block(
      width: 100%, height: 100%, inset: (x: 56pt, y: 44pt),
      fill: gradient.linear(angle: 90deg, (c.bg, 0%), (c.bg, 58%), (c.accent-subtle, 100%)),
      {
        logo(58pt)
        v(1fr)
        text(size: 52pt, weight: 600, tracking: -0.035em)[El agente negocia. \ Tú decides.]
        v(26pt)
        block(width: 500pt, text(size: 23pt, fill: c.soft)[Compras B2B por volumen: de la búsqueda a la firma verificable.])
        v(34pt)
        grid(
          columns: (1fr, auto), align: (left + horizon, right + horizon),
          text(size: 18pt, fill: c.muted)[Hackfinance · Madrid Engineering Week],
          text(size: 17pt, badge(tono: "plano", ico: "clock")[7 minutos]),
        )
        v(1fr)
        text(size: 16pt, fill: c.muted)[El agente negocia; la persona decide y firma.]
      },
    ),
    block(
      width: 100%, height: 100%, fill: c.panel, stroke: (left: 1pt + c.line),
      inset: (x: 42pt, y: 46pt),
      {
        text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[DECISIÓN DE COMPRA · ILUSTRATIVO]
        v(28pt)
        text(size: 15pt, fill: c.muted)[Rodamiento 6204-2RS · 5.000 ud]
        v(6pt)
        text(size: 40pt, weight: 600, tracking: -0.02em)[8.600,00 €]
        v(4pt)
        text(size: 15pt, fill: c.muted)[1,72 €/ud · Vendedor A · mock-a]
        v(24pt)
        grid(
          columns: (1fr, 1fr), row-gutter: 12pt, column-gutter: 8pt,
          text(size: 15pt, badge(tono: "ok", ico: "shield-check")[Confianza alta · 86]),
          text(size: 15pt, badge(tono: "ok")[Precio normal]),
          text(size: 15pt, badge(tono: "neutro", ico: "wallet")[Encaje: within_budget]),
          text(size: 15pt, badge(ico: "clock")[Firma pendiente]),
        )
        v(14pt)
        text(size: 13pt, fill: c.muted)[Confianza calculada · precio filtrado · encaje contra tesorería]
        v(26pt)
        regla
        v(14pt)
        let porque(k, v) = block(below: 7pt, grid(
          columns: (1fr, auto), align: (left + horizon, right + horizon),
          text(size: 13.5pt, fill: c.muted, k), text(size: 13.5pt, fill: c.soft, v),
        ))
        porque([Confianza], [86 · banda high])
        porque([Precio], [normal · sin anomalía])
        porque([Encaje], [within_budget · 84 %])
        v(1fr)
        text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[EL RECORRIDO]
        v(14pt)
        grid(
          columns: (auto, auto, auto, auto, auto, auto, auto), column-gutter: 7pt, align: horizon,
          [#text(font: mono, size: 12pt, fill: c.muted)[01] #h(3pt) #text(size: 17pt, weight: 500)[Busca]],
          flecha,
          [#text(font: mono, size: 12pt, fill: c.muted)[02] #h(3pt) #text(size: 17pt, weight: 500)[Filtra]],
          flecha,
          [#text(font: mono, size: 12pt, fill: c.muted)[03] #h(3pt) #text(size: 17pt, weight: 500)[Negocia]],
          flecha,
          [#text(font: mono, size: 12pt, fill: c.muted)[04] #h(3pt) #text(size: 17pt, weight: 500)[Firma]],
        )
        v(22pt)
        text(size: 14pt, fill: c.muted)[Datos de ejemplo, no reales.]
      },
    ),
  )
  #place(bottom + right, dx: -42pt, dy: -30pt, text(size: 17pt, fill: c.muted, number-width: "tabular")[0:00–0:20])
]

// 2 ─ El problema ───────────────────────────────────────────────────
#slide[
  #titulo[Comprar por volumen se decide a ciegas]
  #let fila(n, t, d) = block({
    regla
    grid(
      columns: (54pt, 500pt, 1fr), column-gutter: 0pt,
      inset: (y: 18pt), align: (left + horizon, left + horizon, left + horizon),
      text(font: mono, size: 15pt, fill: c.muted)[#n],
      text(size: 26pt, weight: 600, tracking: -0.015em, t),
      suave(d, tam: 21pt),
    )
  })
  #fila("01", [El precio real no está publicado], [Se regatea por chat, vendedor a vendedor, en varios idiomas. Sin horas, se paga el de lista.])
  #v(46pt)
  #fila("02", [Lo más barato es lo más peligroso], [Precios gancho, falsificaciones y reseñas infladas.])
  #v(46pt)
  #fila("03", [El precio de lista no es el coste], [Faltan envío, aranceles, IVA de importación, divisa y coste de capital.])
  #v(46pt)
  #fila("04", [Nadie puede demostrar qué se decidió], [Ni con qué datos, ni si la tesorería lo aguantaba.])
  #v(18pt)
  #pie[0:20–0:55]
]

// 3 ─ La propuesta: 8 pasos ──────────────────────────────────────────
#slide[
  #titulo[La propuesta: 8 pasos, en este orden]
  #let quien = (ia: ([IA y código], c.muted), cod: ([Código], c.accent), per: ([Persona], c.ink))
  #let etapa(n, nombre, detalle, q) = {
    let (etq, color) = quien.at(q)
    block(width: 100%, height: 250pt, stroke: (top: 4pt + color), inset: (top: 14pt, right: 6pt), {
      text(font: mono, size: 13pt, fill: c.muted)[#n]
      v(10pt)
      text(size: 21pt, weight: 600, tracking: -0.015em, nombre)
      v(5pt)
      text(size: 17pt, fill: c.soft, detalle)
      place(bottom + left, text(size: 14pt, weight: 500, fill: color, etq))
    })
  }
  #grid(
    columns: (1fr,) * 8, column-gutter: 8pt,
    etapa("1", [Perfila], [Empresa, políticas, CSV], "ia"),
    etapa("2", [Busca], [Ofertas de varias plataformas], "ia"),
    etapa("3", [Confianza], [Señales, banda, versión], "cod"),
    etapa("4", [Precio], [Mediana, MAD, gate], "cod"),
    etapa("5", [Regatea], [Chat del vendedor], "ia"),
    etapa("6", [Encaje], [Coste total vs tesorería], "cod"),
    etapa("7", [Decide], [Dashboard con el porqué], "per"),
    etapa("8", [Firma], [Ed25519 verificable], "per"),
  )
  #v(28pt)
  #grid(
    columns: (auto, auto, auto, 1fr), column-gutter: 26pt,
    align: (left + horizon, left + horizon, left + horizon, right + horizon),
    grid(columns: (auto, auto), column-gutter: 8pt, align: horizon, rect(width: 9pt, height: 9pt, fill: c.muted), text(size: 16pt, fill: c.soft)[IA y código]),
    grid(columns: (auto, auto), column-gutter: 8pt, align: horizon, rect(width: 9pt, height: 9pt, fill: c.accent), text(size: 16pt, fill: c.soft)[Código]),
    grid(columns: (auto, auto), column-gutter: 8pt, align: horizon, rect(width: 9pt, height: 9pt, fill: c.ink), text(size: 16pt, fill: c.soft)[Persona]),
    text(size: 15pt, fill: c.muted)[8 pasos · una sola firma humana],
  )
  #v(26pt)
  #block(width: 100%, fill: c.panel, stroke: (left: 3pt + c.accent), inset: (x: 18pt, y: 13pt), [
    #text(size: 20pt, fill: c.soft)[Ningún paso se salta: una oferta con precio anómalo o poca confianza no llega a Regatea.]
    #v(2pt)
    #text(size: 15pt, fill: c.muted)[Y ninguna llega a compra sin firma.]
  ])
  #v(1fr)
  #text(size: 30pt, weight: 500, tracking: -0.015em)[La IA donde aporta; los números, en código determinista.]
  #v(16pt)
  #pie[0:55–1:35]
]

// 4 ─ Tres invariantes ─────────────────────────────────────────────
#slide[
  #titulo[Tres invariantes]
  #let invariante(n, ico, t, cuerpo, nota) = block(
    width: 100%, height: 392pt, fill: c.panel, stroke: (top: 3pt + c.accent), inset: 26pt,
    {
      grid(columns: (1fr, auto), align: horizon,
        text(font: mono, size: 14pt, fill: c.muted)[#n],
        icono(ico, c.accent, tam: 30pt),
      )
      v(22pt)
      text(size: 29pt, weight: 600, tracking: -0.02em, t)
      v(16pt)
      text(size: 20pt, fill: c.soft, cuerpo)
      place(bottom + left, text(font: mono, size: 13pt, fill: c.muted)[#nota])
    },
  )
  #grid(
    columns: (1fr, 1fr, 1fr), column-gutter: 20pt,
    invariante("01", "shield-check", [La confianza se calcula, no se opina], [Antigüedad, ventas, catálogo y reseñas. Score, banda y versión del modelo en cada oferta.], "trust.compute() · v1"),
    invariante("02", "ban", [El precio se filtra antes de negociar], [Cero presupuesto de negociación en ofertas anómalas. El gate decide antes de abrir el chat.], "sanity.check() → gate"),
    invariante("03", "pen-line", [Sin firma humana no hay compromiso], [Ed25519 en el navegador. La clave privada no sale del dispositivo.], "JCS → Ed25519 → WORM"),
  )
  #v(22pt)
  #suave(tam: 21pt)[Si una de las tres falla, la oferta no avanza. No se compensa con las otras.]
  #pie[1:35–2:05]
]

// 5 ─ Arquitectura ────────────────────────────────────────────────
#slide[
  #titulo[Arquitectura]
  #let capa(k, t, d) = block(
    width: 100%, height: 184pt, fill: c.panel, stroke: (top: 2pt + c.line-strong), inset: 22pt,
    {
      kicker(k)
      v(8pt)
      text(size: 25pt, weight: 600, tracking: -0.015em, t)
      v(6pt)
      text(size: 18pt, fill: c.soft, d)
    },
  )
  #grid(
    columns: (1fr, 1fr), column-gutter: 12pt, row-gutter: 12pt,
    capa("web", [Next.js 15 + BFF], [Onboarding, misión, dashboard y gate. La UI no calcula: muestra lo que devuelve la API.]),
    capa("orchestrator", [FastAPI + LangGraph], [Agentes Intake, Planner, Enrichment, Gate, Evaluator y Supervisor, más el negociador.]),
    capa("browser worker", [Puppeteer · Playwright · Camoufox], [Scraping y chat del vendedor. Las credenciales se quedan dentro del worker.]),
    capa("data / infra", [Postgres 16 + pgvector + RLS], [Redis, S3 Object Lock, Keycloak, Vault y OpenTelemetry. Un tenant, un espacio.]),
  )
  #v(12pt)
  #block(width: 100%, height: 78pt, fill: c.accent-subtle, stroke: (left: 4pt + c.accent), inset: (x: 22pt, y: 10pt), [
    #text(size: 20pt, weight: 500)[LLM Gateway] #h(10pt) #text(font: mono, size: 17pt, fill: c.accent)[/v1/chat/completions] #h(10pt) #text(size: 17pt, fill: c.soft)[compatible OpenAI] \
    #text(size: 16pt, fill: c.soft)[vLLM · llama.cpp · Ollama — modelos autoalojados, sin SDK propietario.]
  ])
  #pie[2:05–2:50]
]

// 6 ─ Motores deterministas ────────────────────────────────────────
#slide[
  #titulo[Motores deterministas: seis cálculos, cero opiniones]
  #let motor(k, t, d) = block(
    width: 100%, height: 190pt, fill: c.panel, stroke: (top: 2pt + c.line-strong), inset: 20pt,
    {
      kicker(k)
      v(9pt)
      text(size: 23pt, weight: 600, tracking: -0.015em, t)
      v(7pt)
      text(size: 18pt, fill: c.soft, d)
    },
  )
  #grid(
    columns: (1fr, 1fr, 1fr), column-gutter: 14pt, row-gutter: 13pt,
    motor("money", [Money + FX], [Céntimos enteros, EUR/USD/CNY. Tipos como decimales, nunca floats.]),
    motor("finance", [CSV + landed cost], [Envío, aranceles, IVA y capital. La suma cuadra al céntimo.]),
    motor("trust", [Confianza], [Señales, config y model_version. Reproducible bit a bit.]),
    motor("sanity", [Sanidad de precio], [Mediana y MAD; bandas desde config, no desde el LLM.]),
    motor("gate_matrix", [Matriz de gate], [3×3 puro. Barato y poco fiable escala a descarte.]),
    motor("mcda", [Ranking MCDA], [Restricciones duras primero; pesos del perfil y motivo por criterio.]),
  )
  #v(1fr)
  #grid(
    columns: (1fr, auto), align: (left + horizon, right + horizon),
    suave(tam: 20pt)[TypeScript y Python pasan los mismos vectores.],
    text(size: 16pt, fill: c.muted)[Ningún motor llama a un modelo.],
  )
  #v(14pt)
  #pie[2:50–3:25]
]

// 7 ─ Confianza del vendedor ───────────────────────────────────────
#slide[
  #titulo[Confianza: de las señales a la banda]
  #grid(
    columns: (600pt, 1fr), column-gutter: 44pt,
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[CÓMO SE CALCULA]
      v(6pt)
      let senal(k, t) = block(width: 100%, stroke: (bottom: 1pt + c.line), inset: (y: 20pt), grid(
        columns: (112pt, 1fr), column-gutter: 14pt, align: (left + horizon, left + horizon),
        text(font: mono, size: 13.5pt, fill: c.accent)[#k],
        text(size: 18pt, fill: c.soft, t),
      ))
      senal("normalize", [Normalización saturada; el x_sat de cada señal sale de config.])
      senal("bayes", [Suavizado bayesiano: una reseña de 5,0 no vale un 5,0.])
      senal("wilson", [Cota inferior de Wilson al nivel de confianza configurado.])
      senal("flags", [Ráfagas, 5 estrellas anómalas o texto duplicado: banda máxima low.])
      senal("min_signals", [Menos señales de las exigidas: insufficient_data.])
      senal("model_version", [Mismo score y banda con la misma instantánea y config.])
    },
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[MISMA REGLA, DOS VENDEDORES]
      v(10pt)
      let vendedor(titulo, detalle, score, banda, tono, etiqueta) = block(
        width: 100%, fill: c.panel, stroke: (left: 3pt + tono), inset: 24pt,
        {
          grid(columns: (1fr, auto), align: (left + top, right + horizon),
            [ #text(size: 17pt, weight: 500)[#titulo] \ #text(size: 14pt, fill: c.muted)[#detalle] ],
            text(size: 44pt, weight: 600, tracking: -0.02em)[#score],
          )
          v(12pt)
          text(size: 14pt, badge(tono: etiqueta)[#banda])
        },
      )
      vendedor([1 reseña de 5,0], [5,00 bruto → 4,52 ajustado], [38], [banda low], c.warn, "warn")
      v(16pt)
      vendedor([500 reseñas de 4,8], [4,80 bruto → 4,79 ajustado], [86], [banda high], c.good, "ok")
      v(18pt)
      text(size: 14pt, fill: c.muted)[Ilustrativo: mismo config y misma versión del modelo. Cada oferta viaja con su banda y su model_version.]
    },
  )
  #v(1fr)
  #suave(tam: 21pt)[Una reseña perfecta no compra confianza; quinientas regulares sí pueden ganarla.]
  #v(16pt)
  #pie[3:25–3:55]
]

// 8 ─ Precio y gate ───────────────────────────────────────────────
#slide[
  #titulo[Precio: primero se filtra, después se negocia]
  #grid(
    columns: (590pt, 1fr), column-gutter: 40pt,
    {
      let criterio(n, k, t) = block(width: 100%, stroke: (bottom: 1pt + c.line), inset: (y: 11pt), grid(
        columns: (26pt, 1fr), column-gutter: 8pt, align: (left + horizon, left + top),
        text(font: mono, size: 13pt, fill: c.muted)[#n],
        [ #text(size: 19pt, weight: 500)[#k] \ #text(size: 16pt, fill: c.soft)[#t] ],
      ))
      criterio("01", [Mediana + MAD], [Desviación absoluta mediana: robusta ante un outlier.])
      criterio("02", [Fallback IQR], [Si la muestra no da para MAD, se usa el rango intercuartílico.])
      criterio("03", [Bandas asimétricas], [El lado barato usa umbrales más estrictos que el caro.])
      criterio("04", [−60 % bajo la mediana], [Al menos atypical. La confianza alta no lo compensa.])
      criterio("05", [insufficient_reference], [Siempre al gate: no se negocia a ciegas.])
      v(10pt)
      text(size: 14.5pt, fill: c.muted)[Bandas y versiones salen de config; el LLM no clasifica precios.]
    },
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[MATRIZ 3×3 · PRECIO × CONFIANZA]
      v(8pt)
      let res(t, tono) = text(size: 15pt, badge(tono: tono)[#t])
      table(
        columns: (96pt, 1fr, 1fr, 1fr),
        stroke: (x, y) => if y > 0 { (top: 1pt + c.line, bottom: 1pt + c.line) },
        inset: (x: 7pt, y: 13pt), align: left + horizon,
        fill: (x, y) => if y == 0 { c.raised },
        table.header(
          [],
          text(size: 13pt, fill: c.muted)[Alta/media],
          text(size: 13pt, fill: c.muted)[Baja],
          text(size: 13pt, fill: c.muted)[No fiable],
        ),
        text(size: 16pt)[Normal], res([Negociar], "ok"), res([Persona], "warn"), res([Descartar], "bad"),
        text(size: 16pt)[Atípico], res([Persona], "warn"),
        table.cell(
          fill: c.bad-subtle,
          stroke: (top: 2pt + c.bad, bottom: 2pt + c.bad, left: 2pt + c.bad, right: 2pt + c.bad),
          align: center + horizon, res([Escala], "bad"),
        ),
        res([Descartar], "bad"),
        text(size: 16pt)[Implausible], res([Descartar], "bad"), res([Descartar], "bad"), res([Descartar], "bad"),
      )
      v(10pt)
      peq[#icono("ban", c.bad) #h(5pt) Negociación: 0 llamadas si el precio es atípico o implausible.]
      v(2pt)
      peq[Barato y poco fiable es la señal de fraude más clara: sube la severidad.]
    },
  )
  #v(1fr)
  #text(size: 21pt, fill: c.soft)[El filtro se paga antes: no se gasta una sola conversación en una oferta que no puede comprarse.]
  #v(16pt)
  #pie[3:55–4:30]
]

// 9 ─ Negociación ────────────────────────────────────────────────
#slide[
  #titulo[Negociación: el modelo redacta, el código limita]
  #grid(
    columns: (620pt, 1fr), column-gutter: 44pt,
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[PLAYBOOK · 6 PASOS]
      v(8pt)
      let paso(n, t, d) = block(width: 100%, stroke: (bottom: 1pt + c.line), inset: (y: 14pt), grid(
        columns: (24pt, 1fr), column-gutter: 8pt, align: (left + horizon, left + top),
        text(font: mono, size: 13pt, fill: c.muted)[#n],
        [ #text(size: 20pt, weight: 500)[#t] \ #text(size: 15pt, fill: c.muted)[#d] ],
      ))
      paso("1", [Abrir con contexto], [Producto, volumen y uso real.])
      paso("2", [Ancla justificada], [Contra mediana y referencias del mercado.])
      paso("3", [Pedir volumen primero], [Escalado por tramos antes de mover precio.])
      paso("4", [Escalera de contraofertas], [Hasta target_discount, nunca max_discount.])
      paso("5", [Detectar cierre], [Señales de aceptación y siguiente paso concreto.])
      paso("6", [Resumen por escrito], [Qué, cuánto, cuándo y en qué divisa.])
    },
    {
      block(width: 100%, fill: c.panel, stroke: (top: 3pt + c.bad), inset: 20pt, {
        text(size: 19pt, weight: 600)[Guardrails antes de cada envío]
        v(8pt)
        let g(t) = block(below: 12pt, grid(
          columns: (12pt, 1fr), column-gutter: 8pt, align: (left + top, left + top),
          move(dy: 3pt, text(fill: c.bad, size: 13pt)[•]), text(size: 16pt, fill: c.soft, t),
        ))
        g([No supera max_discount ni el volumen pedido.])
        g([Sin prepago, garantías ni penalizaciones no autorizadas.])
        g([Tope de rondas, mensajes y tokens por conversación.])
        g([Pago fuera de plataforma o datos sensibles: persona.])
        g([Nunca acepta un compromiso vinculante.])
      })
      v(12pt)
      peq[#icono("clock", c.muted) #h(4pt) Fase 1 semiautomática: cada mensaje espera aprobación.]
      v(4pt)
      peq[#icono("pen-line", c.muted) #h(4pt) Takeover: el agente no envía mientras una persona tiene el control.]
    },
  )
  #v(1fr)
  #text(size: 21pt, fill: c.soft)[El LLM redacta y extrae la oferta; los límites se comprueban en código antes de enviar.]
  #v(16pt)
  #pie[4:30–5:05]
]

// 10 ─ Encaje financiero ─────────────────────────────────────────
#slide[
  #titulo[El encaje se mide con el coste real]
  #grid(
    columns: (600pt, 1fr), column-gutter: 44pt,
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[COSTE TOTAL · 5.000 UD · ILUSTRATIVO]
      v(6pt)
      table(
        columns: (1fr, 158pt),
        stroke: (x, y) => (bottom: 1pt + c.line),
        inset: (x: 6pt, y: 16pt), align: (left + horizon, right + horizon),
        [Precio unitario × cantidad], [8.000,00 €],
        [Envío], [240,00 €],
        [Seguro], [85,00 €],
        [Aranceles], [320,00 €],
        [IVA de importación], [1.344,00 €],
        [Coste de capital], [96,00 €],
        [Divisa (FX)], [18,00 €],
        table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), text(weight: 600)[Total]), table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), text(weight: 600)[10.103,00 €]),
      )
      v(12pt)
      peq[Precio de lista 1,60 €/ud; coste real 2,02 €/ud.]
    },
    {
      block(width: 100%, fill: c.panel, stroke: (top: 3pt + c.accent), inset: 22pt, {
        text(size: 15pt, fill: c.muted)[Presupuesto de la categoría]
        v(6pt)
        text(size: 27pt, weight: 600)[12.000,00 €]
        v(18pt)
        block(width: 100%, height: 12pt, fill: c.raised, {
          place(left + top, rect(width: 84.2%, height: 12pt, fill: c.accent))
        })
        v(14pt)
        grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
          text(size: 14pt, fill: c.soft)[10.103,00 € · 84 %],
          text(size: 14pt, fill: c.muted)[Quedan 1.897,00 €],
        )
        v(18pt)
        text(size: 15pt, badge(tono: "ok", ico: "circle-check")[within_budget])
        v(14pt)
        text(size: 15pt, fill: c.muted)[stretch · out_of_budget: si el total pasa del umbral o de la caja.]
      })
      v(14pt)
      peq[Tesorería proyectada a la fecha de pago: 18.400,00 €.]
      v(4pt)
      peq[El veredicto y el motivo numérico viajan con la oferta.]
    },
  )
  #v(1fr)
  #text(size: 23pt, weight: 500, tracking: -0.01em)[Nunca se compara el precio de lista con la caja.]
  #v(16pt)
  #pie[5:05–5:35]
]

// 11 ─ Decisión y firma ──────────────────────────────────────────
#slide[
  #titulo[Decide una persona. Lo demuestra la firma.]
  #grid(
    columns: (640pt, 1fr), column-gutter: 44pt,
    {
      block(width: 100%, fill: c.panel, stroke: (top: 3pt + c.accent), inset: 26pt, {
        grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
          text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[LISTO PARA DECIDIR],
          text(size: 13pt, fill: c.muted)[SLA 05:20],
        )
        v(16pt)
        text(size: 25pt, weight: 600, tracking: -0.015em)[Rodamiento 6204-2RS · 5.000 ud]
        v(8pt)
        [#text(size: 32pt, weight: 600)[10.103,00 €] #h(8pt) #text(size: 15pt, fill: c.muted)[coste total]]
        v(18pt)
        grid(
          columns: (1fr, 1fr), row-gutter: 12pt, column-gutter: 6pt,
          text(size: 14pt, badge(tono: "ok", ico: "shield-check")[Confianza alta · 86]),
          text(size: 14pt, badge(tono: "ok")[Precio normal]),
          text(size: 14pt, badge(tono: "neutro", ico: "wallet")[within_budget]),
          text(size: 14pt, badge(ico: "clock")[Firma pendiente]),
        )
        v(20pt)
        regla
        v(16pt)
        grid(columns: (auto, auto, auto, 1fr), column-gutter: 8pt, align: horizon,
          box(fill: c.accent, inset: (x: 12pt, y: 6pt), text(size: 14pt, fill: c.bg, weight: 500)[Seguir]),
          box(fill: c.raised, inset: (x: 12pt, y: 6pt), text(size: 14pt, fill: c.soft)[Renegociar]),
          box(fill: c.raised, inset: (x: 12pt, y: 6pt), text(size: 14pt, fill: c.soft)[Descartar]),
          text(size: 13pt, fill: c.muted)[cada acción se firma],
        )
      })
      v(16pt)
      peq[El porqué está en la ficha: banda, saneamiento, encaje y contribución de cada criterio.]
    },
    {
      text(font: mono, size: 13pt, fill: c.muted, tracking: 0.06em)[DE LA DECISIÓN A LA PRUEBA]
      v(6pt)
      let hito(k, t, d) = block(width: 100%, stroke: (bottom: 1pt + c.line), inset: (y: 14pt), grid(
        columns: (88pt, 1fr), column-gutter: 14pt, align: (left + horizon, left + top),
        text(font: mono, size: 14pt, fill: c.accent)[#k],
        [ #text(size: 19pt, weight: 500)[#t] \ #text(size: 14.5pt, fill: c.muted)[#d] ],
      ))
      hito("payload", [JSON canónico], [RFC 8785 JCS, mismos bytes en TS y Python.])
      hito("Ed25519", [Firma en el navegador], [La clave privada no sale del dispositivo.])
      hito("chain", [Cadena de hashes], [Una cadena por tenant, con bloqueo de escritura.])
      hito("WORM", [S3 Object Lock], [Modo compliance: ni el operador borra la prueba.])
      v(14pt)
      grid(
        columns: (auto, auto), row-gutter: 6pt, column-gutter: 6pt,
        text(size: 14pt, badge(tono: "neutro", ico: "fingerprint")[Sesión fija 15 min]),
        text(size: 14pt, badge(tono: "warn", ico: "fingerprint")[Importe alto ⇒ reauth]),
        text(size: 14pt, badge(tono: "neutro", ico: "shield-check")[Doble control]),
      )
      v(10pt)
      text(size: 14pt, fill: c.muted)[La ventana no se desliza: firmar no la alarga.]
    },
  )
  #v(24pt)
  #block(width: 100%, fill: c.panel, stroke: (top: 1pt + c.line), inset: (x: 22pt, y: 14pt), {
    grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
      text(font: mono, size: 12.5pt, fill: c.muted, tracking: 0.05em)[SESIÓN DE FIRMA · 15 MINUTOS FIJOS],
      text(size: 13pt, fill: c.muted)[abre con passkey · firmar no la alarga],
    )
    v(16pt)
    block(width: 100%, height: 6pt, fill: c.accent-subtle, {
      place(left + top, rect(width: 53%, height: 6pt, fill: c.accent))
      place(left + top, dx: 0pt, dy: -5pt, rect(width: 2pt, height: 16pt, fill: c.ink))
      place(left + top, dx: 26%, dy: -5pt, rect(width: 2pt, height: 16pt, fill: c.ink))
      place(left + top, dx: 53%, dy: -5pt, rect(width: 2pt, height: 16pt, fill: c.ink))
      place(left + top, dx: 100% - 2pt, dy: -5pt, rect(width: 2pt, height: 16pt, fill: c.bad))
    })
    v(8pt)
    grid(columns: (1fr, 1fr, 1fr), align: (left, center, right),
      text(size: 12.5pt, fill: c.soft)[0 min · abre],
      text(size: 12.5pt, fill: c.soft)[8 min · dos firmas],
      text(size: 12.5pt, fill: c.bad)[15 min · caduca],
    )
  })
  #v(1fr)
  #text(size: 22pt, fill: c.soft)[Cada firma incluye importe, banda de confianza, saneamiento y versión del modelo.]
  #v(16pt)
  #pie[5:35–6:20]
]

// 12 ─ Estado y cierre ───────────────────────────────────────────
#slide[
  #titulo[Dónde estamos]
  #let columna(t, filas, alto: 360pt) = block(
    width: 100%, height: alto, fill: c.panel, stroke: (top: 2pt + c.line-strong), inset: 22pt,
    {
      text(size: 21pt, weight: 600)[#t]
      v(12pt)
      set text(size: 18pt)
      set list(marker: text(fill: c.accent)[•], indent: 0pt, body-indent: 9pt, spacing: 1em)
      filas
    },
  )
  #let cifra(n, t) = block(below: 10pt, grid(
    columns: (74pt, 1fr), column-gutter: 10pt, align: (left + horizon, left + horizon),
    text(size: 26pt, weight: 600, tracking: -0.02em)[#n], text(size: 15pt, fill: c.soft, t),
  ))
  #grid(
    columns: (1fr, 1fr, 1fr), column-gutter: 18pt,
    columna([Ya funciona], [
      - Onboarding y CSV activable
      - Dos plataformas con chat
      - Motores TS/Python con vectores
      - Gate y dashboard firmados
      - Firma Ed25519 y cadena
      - Negociación semiautomática
      - RLS por tenant y WORM
      - Verificación de la cadena
    ]),
    columna([Siguiente], [
      - Adaptadores reales (F2)
      - Calibración de confianza
      - ClickHouse y dbt
      - Sellado RFC 3161
      - Modelos autoalojados
      - SSO empresarial y PSD2
      #v(22pt)
      #text(size: 15pt, fill: c.muted)[El alcance no cambia: primero la prueba, después la escala.]
    ]),
    columna([Números], {
      cifra([6], [lanes en paralelo])
      cifra([11], [jobs de CI local])
      cifra([6], [imágenes de contenedor])
      cifra([1.687], [tests Python en CI])
      cifra([31], [criterios de aceptación])
      v(2pt)
      text(size: 14.5pt, fill: c.soft)[Cobertura: money 99,6 % · crypto 98,1 % · scoring 78,1 % (ratchet).]
      v(8pt)
      text(size: 14.5pt, fill: c.soft)[0 marketplaces reales en CI.]
    }),
  )
  #v(1fr)
  #text(size: 27pt, weight: 600, tracking: -0.02em)[La IA negocia. El código calcula. Una persona firma.]
  #v(16pt)
  #pie[6:20–7:00]
]

// 13 ─ Anexo: guion ────────────────────────────────────────────
#slide[
  #grid(columns: (1fr, auto), align: (left + horizon, right + horizon),
    titulo[Guion de 7 minutos],
    text(size: 15pt, badge(tono: "plano")[No se presenta]),
  )
  #v(18pt)
  #set text(size: 17pt)
  #table(
    columns: (58pt, 1fr, 132pt, 92pt),
    stroke: (x, y) => if y > 0 { (top: 1pt + c.line, bottom: 1pt + c.line) },
    inset: (x: 10pt, y: 8pt), align: (left + horizon, left + horizon, right + horizon, right + horizon),
    fill: (x, y) => if y == 0 { c.raised },
    table.header(
      text(size: 14pt, fill: c.muted)[Nº], text(size: 14pt, fill: c.muted)[Tema],
      text(size: 14pt, fill: c.muted)[Desde–hasta], text(size: 14pt, fill: c.muted)[Seg.],
    ),
    [01], [Portada], [0:00–0:20], [20],
    [02], [El problema], [0:20–0:55], [35],
    [03], [La propuesta: 8 pasos], [0:55–1:35], [40],
    [04], [Tres invariantes], [1:35–2:05], [30],
    [05], [Arquitectura], [2:05–2:50], [45],
    [06], [Motores deterministas], [2:50–3:25], [35],
    [07], [Confianza del vendedor], [3:25–3:55], [30],
    [08], [Precio y gate], [3:55–4:30], [35],
    [09], [Negociación], [4:30–5:05], [35],
    [10], [Encaje financiero], [5:05–5:35], [30],
    [11], [Decisión y firma], [5:35–6:20], [45],
    [12], [Estado y cierre], [6:20–7:00], [40],
    table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), text(weight: 600)[Total]),
    table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), text(weight: 600)[12 diapositivas]),
    table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), align: right + horizon, text(weight: 600)[7:00]),
    table.cell(stroke: (top: 1.5pt + c.line-strong, bottom: none), align: right + horizon, text(weight: 600)[420]),
  )
  #v(10pt)
  #peq[Si el tiempo aprieta, se recorta el bloque de motores (35 s), nunca la firma.]
  #v(1fr)
  #grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 18pt,
    [ #text(font: mono, size: 12pt, fill: c.muted)[APERTURA] \ #text(size: 24pt, weight: 600)[0:20] ],
    [ #text(font: mono, size: 12pt, fill: c.muted)[CONTEXTO · 2–4] \ #text(size: 24pt, weight: 600)[1:45] ],
    [ #text(font: mono, size: 12pt, fill: c.muted)[PRODUCTO · 5–11] \ #text(size: 24pt, weight: 600)[4:15] ],
    [ #text(font: mono, size: 12pt, fill: c.muted)[CIERRE · 12] \ #text(size: 24pt, weight: 600)[0:40] ],
  )
  #v(22pt)
  #pie[anexo · 0:00–7:00 · no se presenta]
]
