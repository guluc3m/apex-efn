// Compilar con make, desde esta carpeta.
// Cada paso de animación es una página del PDF; se presenta a pantalla completa con cualquier visor.
// Página de 1280×720 pt: las medidas de DESIGN.md se escalan directamente para proyectar.
#import "@preview/touying:0.6.1": *
#import themes.default: slide
#import "tema.typ": *

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
#set text(font: fuente, fill: c.ink, size: 26pt, lang: "es", number-width: "tabular")
#set par(leading: 0.55em)

#let sin-marco = config-page(margin: 0pt, header: none)
#let titulo(t) = block(below: 30pt, text(size: 44pt, weight: 600, tracking: -0.02em, t))
#let suave(t, tam: 24pt) = text(size: tam, fill: c.soft, t)
#let peq(t) = text(size: 19pt, fill: c.muted, t)
#let cifra(t, tam: 64pt) = text(size: tam, weight: 600, tracking: -0.02em, t)
#let regla = line(length: 100%, stroke: 1pt + c.line)
// Mantiene el hueco de lo que aún no aparece, para que nada salte entre pasos.
#let vis(s, n, cuerpo) = if s >= n { cuerpo } else { hide(cuerpo) }
#let boton(t, ico) = box(fill: c.accent, inset: (x: 16pt, y: 9pt), text(size: 21pt, weight: 500, fill: c.bg)[#icono(ico, c.bg) #h(5pt) #t])

// Pantalla de acceso de la web (login-panel.tsx): marca a la izquierda, campo de puntos a la derecha.
#let acceso(izquierda, derecha: none) = grid(
  columns: (600pt, 680pt), rows: 720pt,
  block(
    width: 100%, height: 100%, inset: (x: margen, y: 40pt),
    fill: gradient.linear(angle: 90deg, (c.bg, 0%), (c.bg, 75%), (c.accent-subtle, 100%)),
    izquierda,
  ),
  block(width: 100%, height: 100%, stroke: (left: 1pt + c.line), {
    place(image("/apps/web/public/login-field.webp", width: 100%, height: 100%, fit: "cover"))
    if derecha != none { place(bottom + left, dx: margen, dy: -40pt, derecha) }
  }),
)

// 1 ───────────────────────────────────────────────────────────────
#slide(config: sin-marco)[
  #acceso(
    [
      #logo(64pt)
      #v(1fr)
      #text(size: 42pt, weight: 600, tracking: -0.03em)[El agente negocia. \ Tú decides. \ Tu firma lo demuestra.]
      #v(14pt)
      #suave[Compras B2B por volumen: buscar, filtrar y regatear, sin comprometer un euro sin una persona.]
      #v(1fr)
      #peq[Hackfinance · Madrid Engineering Week]
    ],
    derecha: block(width: 568pt, fill: c.panel, stroke: 1pt + c.line, inset: 10pt)[
      #set text(size: 21pt)
      #let fila(fondo, a, b, prod, precio, ..bs) = block(width: 100%, fill: fondo, inset: 15pt, below: 4pt)[
        #text(size: 18pt, fill: c.muted)[#a #h(1fr) #b] \
        #text(weight: 500)[#prod] #h(1fr) #text(weight: 600)[#precio] \
        #v(1pt)
        #text(size: 18pt, bs.pos().join(h(7pt)))
      ]
      #block(inset: (x: 15pt, top: 12pt, bottom: 2pt), below: 8pt, text(size: 18pt, fill: c.muted)[Cola de decisión #h(1fr) 2 pendientes])
      #fila(c.raised, [Listo para decidir], [Vendedor A], [Rodamiento 6204-2RS · 5.000 ud], [1,72 €/ud],
        badge(tono: "ok", ico: "shield-check")[Confianza alta · 86], badge(tono: "ok")[Precio normal], badge(ico: "clock")[Pendiente])
      #fila(none, [Vendedor en banda baja], [SLA 05:20], [Válvula de bola DN25 · 800 ud], [12,40 €/ud],
        badge(tono: "warn", ico: "shield-alert")[Confianza baja · 38], badge(tono: "ok")[Precio normal], badge(ico: "clock")[Pendiente])
      #block(inset: (x: 15pt, bottom: 8pt), text(size: 18pt, fill: c.muted)[Muestra ilustrativa, no son datos reales.])
    ],
  )
]

// 2 ───────────────────────────────────────────────────────────────
#slide(repeat: 4, self => {
  let s = self.subslide
  titulo[Comprar por volumen se decide a ciegas]
  let fila(n, t, d) = vis(s, n, block(below: 0pt, {
    regla
    grid(
      columns: (505pt, 1fr), column-gutter: 40pt, inset: (y: 27pt),
      text(size: 30pt, weight: 600, tracking: -0.015em, t), suave(d),
    )
  }))
  fila(1, [El precio real no está publicado], [Se regatea por chat, vendedor a vendedor, en varios idiomas. Sin horas, se paga el de lista.])
  fila(2, [Lo más barato es lo más peligroso], [Precios gancho, falsificaciones y reseñas infladas.])
  fila(3, [El precio de lista no es el coste], [Faltan envío, aranceles, IVA de importación, divisa y coste de capital.])
  fila(4, [Nadie puede demostrar qué se decidió], [Ni con qué datos, ni si la tesorería lo aguantaba.])
})

// 3 ───────────────────────────────────────────────────────────────
#slide[
  #titulo[Lo que existe resuelve solo una parte]
  #set text(size: 23pt)
  #table(
    columns: (330pt, 215pt, 270pt, 1fr),
    stroke: (x, y) => if y > 0 { (top: 1pt + c.line, bottom: 1pt + c.line) },
    inset: (x: 14pt, y: 15pt), align: left + horizon,
    fill: (x, y) => if y == 0 { c.raised } else if x == 3 { c.accent-subtle },
    table.header(
      [], text(size: 20pt, fill: c.muted)[Comparadores], text(size: 20pt, fill: c.muted)[Suites de compras], logo(32pt),
    ),
    ..comparativa.map(f => (text(weight: 500, f.at(0)), text(fill: c.muted, f.at(1)), text(fill: c.muted, f.at(2)), text(weight: 500, f.at(3)))).flatten(),
  )
]

// 4 ───────────────────────────────────────────────────────────────
#slide(repeat: 5, self => {
  let s = self.subslide
  titulo[Ocho pasos, en este orden]
  let quien = (ia: ([IA y código], c.muted), cod: ([Código], c.accent), per: ([Persona], c.ink))
  // Se mueven las líneas, no las cajas: el recorrido avanza por la regla superior.
  let etapa(n, nombre, detalle, q) = {
    let (etq, color) = quien.at(q)
    let barra = if s < n { c.line } else if s >= 5 { color } else { c.accent }
    block(width: 100%, height: 300pt, stroke: (top: 4pt + barra), inset: (top: 16pt, right: 8pt), vis(s, n, {
      text(size: 26pt, weight: 600, tracking: -0.015em, nombre)
      v(4pt)
      text(size: 22pt, fill: c.soft, detalle)
      place(bottom + left, vis(s, 5, text(size: 20pt, weight: 500, fill: color, etq)))
    }))
  }
  grid(
    columns: (1fr,) * 8, column-gutter: 8pt,
    etapa(1, [Perfila], [Empresa, políticas, CSV financiero], "ia"),
    etapa(1, [Busca], [Ofertas de varias plataformas], "ia"),
    etapa(2, [Confianza], [Del vendedor, calculada], "cod"),
    etapa(2, [Precio], [Los anómalos, fuera], "cod"),
    etapa(3, [Regatea], [En el chat del vendedor], "ia"),
    etapa(3, [Encaje], [Coste total frente a tesorería], "cod"),
    etapa(4, [Decide], [Dashboard con el porqué], "per"),
    etapa(4, [Firma], [Ed25519, verificable], "per"),
  )
  v(26pt)
  let frase = if s == 1 { [Primero entiende quién compra y qué hay en el mercado.] }
    else if s == 2 { [Filtra antes de negociar: no se gasta presupuesto en regatear un fraude.] }
    else if s == 3 { [Negocia lo que pasa el filtro y lo contrasta con lo que se puede pagar.] }
    else if s == 4 { [El agente negocia, no compra. Sin firma humana no hay compromiso.] }
    else { [Lo que afecta al dinero lo decide código determinista. La IA conversa y redacta.] }
  text(size: 32pt, weight: 500, tracking: -0.015em, frase)
})

// 5 ───────────────────────────────────────────────────────────────
#slide(repeat: 3, self => {
  let s = self.subslide
  titulo[El precio anómalo cae antes de negociar]
  let ancho = 1168pt
  let x(v) = v / 35 * ancho
  let eje = 130pt
  let alto = 190pt
  block(width: ancho, height: 236pt, {
    if s >= 3 {
      place(dy: 22pt, rect(width: x(7.68), height: alto - 22pt, fill: c.bad-subtle))
      place(dx: x(15.15), dy: 22pt, rect(width: ancho - x(15.15), height: alto - 22pt, fill: c.bad-subtle))
      place(dx: x(11) - 1pt, dy: 22pt, rect(width: 2pt, height: alto - 22pt, fill: c.ink))
      place(dx: x(11) - 70pt, dy: -8pt, text(size: 20pt)[Mediana 11,00 €])
    }
    if s == 2 {
      place(dx: x(12.74) - 1pt, dy: 22pt, rect(width: 2pt, height: alto - 22pt, fill: c.warn))
      place(dx: x(12.74) - 60pt, dy: -8pt, text(size: 20pt, fill: c.warn)[Media 12,74 €])
    }
    place(dy: eje, rect(width: ancho, height: 1pt, fill: c.line-strong))
    for p in (1.10, 10.2, 10.6, 11.0, 11.4, 11.9, 33.0) {
      let fuera = s >= 3 and (p < 2 or p > 30)
      place(dx: x(p) - 10pt, dy: eje - 9.5pt, circle(radius: 10pt, fill: if fuera { c.bad } else { c.accent }))
    }
    place(dx: x(1.10) - 22pt, dy: alto + 10pt, text(size: 20pt, fill: c.soft)[1,10 €])
    place(dx: x(33.0) - 40pt, dy: alto + 10pt, text(size: 20pt, fill: c.soft)[33,00 €])
  })
  v(14pt)
  grid(
    columns: (1fr, 1fr), column-gutter: 48pt,
    vis(s, 2, [
      #suave[Media y desviación típica] \
      #cifra[−1,30] #h(10pt) #text(size: 21pt, badge(tono: "ok")[Parece normal])
    ]),
    vis(s, 3, [
      #suave[Mediana y MAD] \
      #cifra[−8,35] #h(10pt) #text(size: 21pt, badge(tono: "bad")[Implausible, descartada])
    ]),
  )
  v(1fr)
  peq[Ejemplo ilustrativo: siete ofertas, una −90 % y otra +200 %. El lado barato usa umbrales más estrictos.]
})

// 6 ───────────────────────────────────────────────────────────────
#slide(repeat: 4, self => {
  let s = self.subslide
  titulo[La confianza se calcula y no se compensa]
  grid(
    columns: (360pt, 1fr), column-gutter: 56pt,
    {
      suave[1 reseña de 5,0]
      linebreak()
      cifra(if s >= 2 { [4,52] } else { [5,00] })
      v(14pt)
      suave[500 reseñas de 4,8]
      linebreak()
      cifra(if s >= 2 { [4,79] } else { [4,80] })
      v(14pt)
      vis(s, 2, {
        text(font: mono, size: 20pt, fill: c.soft)[(C·m + r·n) / (C + n)]
        linebreak()
        peq[Suavizado bayesiano con C = 25 y m = 4,5 de ejemplo]
      })
    },
    vis(s, 3, {
      let foco = s >= 4
      set text(size: 21pt)
      let (si, per, no) = (badge(tono: "ok")[Negociar], badge(tono: "warn")[Persona], badge(tono: "bad")[Descartar])
      table(
        columns: (150pt, 1fr, 1fr, 1fr),
        stroke: (x, y) => if y > 0 { (top: 1pt + c.line, bottom: 1pt + c.line) },
        inset: (x: 10pt, y: 22pt), align: left + horizon,
        fill: (x, y) => if y == 0 { c.raised },
        table.header(
          [], text(fill: c.muted)[Alta o media], text(fill: c.muted)[Baja], text(fill: c.muted)[No fiable],
        ),
        [Normal], si, per, no,
        [Atípico], per,
        table.cell(stroke: if foco { 2pt + c.bad } else { (top: 1pt + c.line, bottom: 1pt + c.line) }, badge(tono: "bad")[Escala]), no,
        [Implausible], no, no, no,
      )
    }),
  )
  v(1fr)
  vis(s, 4, text(size: 30pt, weight: 500, tracking: -0.015em)[Barato y poco fiable es la señal de fraude más clara: sube la severidad.])
})

// 7 ───────────────────────────────────────────────────────────────
#slide(repeat: 3, self => {
  let s = self.subslide
  titulo[El modelo redacta. Los límites están en código.]
  let mensaje(quien, t) = block(below: 22pt)[
    #text(size: 19pt, fill: c.muted, quien) \
    #text(size: 27pt, t)
  ]
  grid(
    columns: (1fr, 400pt), column-gutter: 40pt,
    block(width: 100%, height: 400pt, fill: c.panel, stroke: 1pt + c.line, inset: 26pt, {
      vis(s, 1, mensaje([Agente], [Para 5.000 unidades, ¿qué escalado de precios aplicáis?]))
      vis(s, 2, mensaje([Vendedor], [10,20 € desde 5.000. Si pagas fuera de la plataforma, 9,10 €.]))
      place(bottom + left, vis(s, 3, block[
        #text(size: 22pt, badge(tono: "bad")[Pago fuera de plataforma])
        #v(4pt)
        #text(size: 25pt, weight: 500)[Conversación detenida. Escalado a una persona.]
      ]))
    }),
    {
      suave[El modelo]
      linebreak()
      text(weight: 500)[Redacta y extrae la oferta del chat]
      v(22pt)
      suave[El código, antes de cada envío]
      for t in ([Descuento máximo], [Volumen solicitado], [Contrapartidas autorizadas], [Rondas y tokens]) {
        block(below: 0pt, inset: (y: 9pt), stroke: (bottom: 1pt + c.line), width: 100%, t)
      }
      v(20pt)
      text(weight: 600)[Nunca acepta un compromiso vinculante.]
    },
  )
  v(1fr)
  peq[Conversación de ejemplo.]
})

// 8 ───────────────────────────────────────────────────────────────
#slide(repeat: 4, self => {
  let s = self.subslide
  // SigningSessionIndicator de la cabecera de la web.
  let (tiempo, vivo) = if s == 1 { ([15:00], true) } else if s < 4 { ([09:12], true) } else { (none, false) }
  place(top + right, dx: -86pt, dy: -94pt, block(fill: c.panel, stroke: 1pt + c.line, inset: (x: 14pt, y: 7pt), {
    set text(size: 20pt)
    text(fill: c.muted)[#icono("pen-line", c.muted) #h(4pt) Firma #h(10pt)]
    if vivo { text(weight: 600, tiempo) } else { badge(tono: "bad")[Sesión caducada] }
  }))
  titulo[Ninguna decisión avanza sin firma]
  // La regla se consume: la ventana es fija y firmar no la alarga.
  let hecho = if s == 1 { 0% } else if s < 4 { 39% } else { 100% }
  block(width: 100%, below: 26pt, {
    rect(width: 100%, height: 4pt, fill: c.accent-subtle, inset: 0pt, align(left, rect(width: hecho, height: 4pt, fill: c.accent)))
    v(-14pt)
    peq[#icono("fingerprint", c.muted) #h(5pt) Una passkey abre 15 minutos fijos #h(1fr) Firmar no los alarga]
  })
  let estado(n) = if n == 3 and s >= 3 and s < 4 {
    badge(tono: "warn", ico: "fingerprint")[Importe alto: reautenticar]
  } else if s >= 4 and n == 3 {
    box(fill: c.accent, inset: (x: 10pt, y: 5pt), text(fill: c.bg, weight: 500)[#icono("fingerprint", c.bg) #h(4pt) Reautenticar para firmar])
  } else if s >= 2 and n < 3 {
    badge(tono: "ok", ico: "badge-check")[Firmado]
  } else {
    badge(ico: "clock")[Pendiente]
  }
  let hash(n, h) = if s >= 2 and n < 3 { text(font: mono, size: 18pt, fill: c.muted, h) }
  {
    set text(size: 23pt)
    table(
      columns: (1fr, 170pt, 170pt, 400pt),
      stroke: (x, y) => if y > 0 { (top: 1pt + c.line, bottom: 1pt + c.line) },
      inset: (x: 14pt, y: 14pt), align: (left + horizon, right + horizon, left + horizon, left + horizon),
      fill: (x, y) => if y == 0 { c.raised },
      table.header(
        text(size: 20pt, fill: c.muted)[Decisión], text(size: 20pt, fill: c.muted)[Importe],
        text(size: 20pt, fill: c.muted)[Hash], text(size: 20pt, fill: c.muted)[Firma],
      ),
      [Rodamiento 6204-2RS · 5.000 ud], [8.600,00 €], hash(1, "7c3e…a91f"), estado(1),
      [Válvula de bola DN25 · 800 ud], [9.920,00 €], hash(2, "b02d…44e8"), estado(2),
      [Tornillo M8 inox · 40.000 ud], [12.400,00 €], [], estado(3),
    )
  }
  v(1fr)
  grid(
    columns: (1fr, 1fr), column-gutter: 40pt,
    suave[La clave privada nunca sale del dispositivo.],
    suave[Cada firma incluye importe, banda, confianza y versión del modelo.],
  )
  v(4pt)
  peq[Datos de ejemplo.]
})

// 9 ───────────────────────────────────────────────────────────────
#slide(repeat: 2, self => {
  let s = self.subslide
  titulo[Arquitectura: la IA, solo donde aporta]
  grid(
    columns: (1fr, 440pt), column-gutter: 48pt,
    {
      set text(size: 23pt)
      let codigo(t) = text(font: mono, size: 20pt, t)
      table(
        columns: (290pt, 1fr),
        stroke: (x, y) => (bottom: 1pt + c.line),
        inset: (x: 14pt, y: 23pt), align: left + horizon,
        table.cell(stroke: (left: 4pt + c.accent, bottom: 1pt + c.line), text(weight: 500)[Motores deterministas]), [Dinero, FX, confianza, precio],
        text(weight: 500)[Orquestador], [FastAPI y LangGraph],
        text(weight: 500)[Pasarela LLM], codigo[/v1/chat/completions],
        text(weight: 500)[Navegador], [Puppeteer, Playwright, BullMQ],
        text(weight: 500)[Web], [Next.js 15 y React 19],
        text(weight: 500)[Datos], [PostgreSQL con RLS, Redis, S3 WORM],
      )
    },
    vis(s, 2, {
      suave[Lo que aporta la IA frontera]
      v(10pt)
      for t in ([Negocia en varios idiomas, chino incluido], [Extrae ofertas de conversaciones desordenadas], [Explica cada recomendación a partir de cifras]) {
        block(below: 0pt, inset: (y: 13pt), stroke: (bottom: 1pt + c.line), width: 100%, t)
      }
      v(16pt)
      suave(tam: 22pt)[Salida estructurada validada y tope de tokens por misión.]
    }),
  )
})

// 10 ──────────────────────────────────────────────────────────────
#slide[
  #titulo[Se paga con lo que ahorra]
  #grid(
    columns: (1fr, 1fr), column-gutter: 64pt,
    [
      #block(below: 14pt, cifra(tam: 112pt)[#icono("arrow-down", c.good, tam: 80pt) 5–20~%])
      #suave[de coste total de adquisición: objetivo de producto]
      #v(26pt)
      #text(weight: 500)[Con 200.000 € al año en compras, un 5 % son 10.000 €.]
    ],
    [
      #suave[Costes acotados]
      #v(6pt)
      #for t in ([Navegador solo para login y chat], [Tope duro de tokens por misión], [Modelos autoalojables, sin atarse a un proveedor]) {
        block(below: 0pt, inset: (y: 15pt), stroke: (bottom: 1pt + c.line), width: 100%, t)
      }
      #v(26pt)
      #text(size: 24pt, badge(tono: "warn")[Pendiente: modelo de ingresos])
    ],
  )
]

// 11 ──────────────────────────────────────────────────────────────
#slide(config: sin-marco)[
  #acceso([
    #logo(64pt)
    #v(1fr)
    #text(size: 42pt, weight: 600, tracking: -0.03em)[El agente negocia. \ Tú decides. \ Tu firma lo demuestra.]
    #v(1fr)
    #text(size: 22pt, fill: c.accent, underline(offset: 4pt)[github.com/guluc3m/apex-efn])
  ])
]
