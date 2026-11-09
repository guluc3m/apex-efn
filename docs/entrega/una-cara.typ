// Compilar con make, desde esta carpeta.
#import "tema.typ": c, comparativa, fuente, logo

#let negro = c.bg
// Verdes de DESIGN.md: accent-subtle como tinta de marca, accent-line como secundario.
#let verde = c.accent-subtle
#let gris = c.accent-line
#let fino = 0.4pt + c.accent-line
#let grueso = 1.2pt + verde
#let banda-sup = 1.75cm
#let banda-inf = 1.05cm
#let lateral = 2.9cm

#set document(title: "APEX-EFN. Hack Quesitos: Resumen de proyecto")
#set text(font: fuente, size: 9.5pt, lang: "es", fill: negro, number-width: "tabular", hyphenate: true)
#set par(leading: 0.62em, spacing: 0.8em, justify: true)
#show "APEX-EFN": it => box(it)
#set page(
  paper: "a4",
  margin: (x: 1.9cm, top: 2.45cm, bottom: 1.7cm),
  header-ascent: 1.3cm,
  footer-descent: 1cm,
  background: {
    place(top + left, rect(width: 100%, height: banda-sup, fill: verde))
    place(top + left, dy: banda-sup, rect(width: 100%, height: 1.2pt, fill: c.accent))
    place(bottom + left, rect(width: 100%, height: banda-inf, fill: verde))
  },
  header: {
    set text(size: 8pt, fill: c.accent)
    grid(
      columns: (1fr, auto), align: (left + horizon, right + horizon),
      logo(25pt), [Apex Platform Entresprise eXchange - Element Fintech Network],
    )
  },
  footer: {
    set text(size: 8pt, fill: c.soft)
    grid(
      columns: (1fr, 1fr), align: (left, right),
      [*APEX-EFN*], link("https://github.com/guluc3m/apex-efn")[*github.com/guluc3m/apex-efn*],
    )
  },
)

#let seccion(n, titulo, cuerpo) = block(above: 0pt, below: 0pt, width: 100%, stroke: (top: fino), inset: (top: 8pt, bottom: 9pt), grid(
  columns: (lateral, 1fr),
  text(weight: 600, fill: verde, grid(columns: (11pt, 1fr), n, par(justify: false, text(hyphenate: false, titulo)))),
  cuerpo,
))
#let pie(t) = block(above: 5pt, below: 9pt, par(justify: false, text(size: 8pt, fill: gris, t)))

#v(5pt)
#block(below: 9pt, par(justify: false, text(size: 18pt, weight: 600, tracking: -0.02em, fill: verde)[Compras B2B negociadas por IA y firmadas por personas]))

#block(below: 13pt, {
  set text(size: 8pt)
  set par(justify: false)
  let m(a, b) = [#text(fill: gris, a) \ #b]
  grid(
    columns: (lateral, auto, 1fr),
    column-gutter: (0pt, 28pt),
    m[Fecha][11 noviembre 2026],
    m[Equipo][Hack Quesitos],
    m[Convocatoria][Hackfinance, Madrid Engineering Week],
  )
})

#seccion([], [Resumen])[
  APEX-EFN es un agente de compras para empresas que adquieren producto por volumen en marketplaces. Localiza ofertas, descarta vendedores y precios poco fiables, negocia en el chat del vendedor y presenta cada trato contrastado con la tesorería de la empresa. La decisión final la toma y la firma una persona.
]

#seccion([1], [Problema])[
  Comprar por volumen en marketplaces sigue siendo un trabajo manual. El precio final rara vez está publicado: se acuerda por chat, vendedor a vendedor y a menudo en otro idioma, de modo que quien no dispone de tiempo para negociar acaba pagando el precio de lista. Ese precio, además, es incompleto, porque no incluye envío, aranceles, IVA de importación, riesgo de divisa ni coste de capital hasta la fecha de pago.

  La oferta más barata suele ser también la de mayor riesgo. Los precios gancho, las falsificaciones y las reseñas infladas se concentran justo donde mira primero el comprador. Cuando la compra se cierra, normalmente entre una conversación privada y una hoja de cálculo, la empresa no puede acreditar quién la aprobó, con qué información ni si su tesorería podía asumirla.
]

#seccion([2], [Solución])[
  APEX-EFN recorre el proceso completo en ocho etapas (figura 1). Tras perfilar a la empresa y cargar su situación financiera, reúne ofertas de varias plataformas y evalúa cada una antes de invertir en ella. La confianza en el vendedor se calcula a partir de su antigüedad, ventas, catálogo y reseñas, con detección de manipulación. El precio se contrasta con el mercado mediante mediana y desviación absoluta. Solo las ofertas que superan ambos controles pasan a negociación.

  #v(3pt)
  #block(above: 6pt, below: 0pt, {
    set text(size: 7.8pt, hyphenate: false)
    set par(justify: false)
    let fases = (([Entender], 2), ([Filtrar], 2), ([Negociar y evaluar], 2), ([Decidir], 2))
    let etapas = (
      ([Perfilado], [IA y código]), ([Búsqueda], [IA y código]),
      ([Confianza], [Código]), ([Precio], [Código]),
      ([Negociación], [IA y código]), ([Encaje], [Código]),
      ([Decisión], [Persona]), ([Firma], [Persona]),
    )
    table(
      columns: (1fr,) * 8,
      stroke: none, inset: (x: 0pt, y: 3.2pt), align: left,
      table.hline(stroke: grueso),
      ..fases.map(((t, n)) => table.cell(colspan: n, text(weight: 600, fill: verde, t))),
      table.hline(stroke: fino),
      ..etapas.enumerate().map(((i, e)) => e.at(0)),
      ..etapas.map(e => text(fill: gris, e.at(1))),
      table.hline(stroke: fino),
    )
  })
  #pie[Figura 1. Etapas del proceso y responsable de cada una.]

  El agente negocia por rondas en el chat del vendedor y no puede aceptar ningún compromiso vinculante. El modelo de lenguaje redacta los mensajes y extrae los términos de la conversación. Los importes, los límites de descuento, las bandas de precio y el ranking los determina código determinista y versionado, de forma que cada resultado es reproducible. El objetivo de producto es reducir entre un 5 % y un 20 % el coste total de adquisición.
]

#seccion([3], [Valor diferencial])[
  Los comparadores muestran precios de lista y reseñas sin tratar. Las suites de compras negocian, pero con proveedores ya homologados y dentro de grandes organizaciones. APEX-EFN se dirige a la compra en mercado abierto, donde el vendedor es desconocido, y reúne en un mismo flujo la negociación, la evaluación del riesgo y la capacidad de pago (tabla 1).

  #block(above: 8pt, below: 0pt, {
    set text(size: 7.8pt, hyphenate: false)
    set par(justify: false)
    table(
      columns: (auto, auto, auto, 1fr),
      stroke: none, align: left + horizon,
      inset: (x, y) => (left: if x == 3 { 8pt } else { 0pt }, right: 5pt, y: 3.6pt),
      fill: (x, y) => if x == 3 { verde },
      table.hline(stroke: grueso),
      [], text(fill: gris)[Comparadores], text(fill: gris)[Suites de compras], logo(15pt),
      table.hline(stroke: fino),
      ..comparativa.map(f => (f.at(0), text(fill: gris, f.at(1)), text(fill: gris, f.at(2)), text(weight: 500, fill: c.ink, f.at(3)))).flatten(),
      table.hline(stroke: fino),
    )
  })
  #pie[Tabla 1. Comparación con las categorías de producto existentes.]

  Tres decisiones de diseño lo distinguen. El control de precios se ejecuta antes de negociar, de modo que no se consume presupuesto en ofertas fraudulentas. La confianza no se promedia con el precio: una oferta anómalamente barata de un vendedor poco fiable se escala a descarte. Y cada decisión queda firmada con Ed25519 junto al importe y la confianza que la persona tenía delante, dentro de una sesión de firma de 15 minutos que no se prolonga al firmar.
]
