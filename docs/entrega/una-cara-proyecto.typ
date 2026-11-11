// APEX-EFN — resumen ejecutivo de una cara (A4).
// Compilar desde docs/entrega:
//   typst compile --root ../.. --font-path fuentes una-cara-proyecto.typ una-cara-proyecto.pdf
#import "tema.typ": c, fuente, mono, logo, icono

#let tinta = rgb("#151517")
#let verde = rgb("#2f6b3a")
#let verde-oscuro = rgb("#173d20")
#let verde-suave = rgb("#f1f5ee")
#let gris = rgb("#5f5f67")
#let linea = rgb("#d8d8d0")

#set document(title: "APEX-EFN · Problema, solución y valor diferencial")
#set page(
  paper: "a4",
  margin: (x: 1.5cm, top: 0cm, bottom: 1.15cm),
  footer-descent: 0.65cm,
  footer: {
    set text(size: 6.9pt, fill: gris)
    grid(
      columns: (1fr, auto),
      [*APEX-EFN* · Hackfinance · Madrid Engineering Week · 11 nov 2026],
      link("https://github.com/guluc3m/apex-efn")[github.com/guluc3m/apex-efn],
    )
  },
)

#set text(font: fuente, size: 10pt, fill: tinta, lang: "es", number-width: "tabular")
#set par(leading: 0.58em, spacing: 0.7em, justify: true)

// Cabecera a sangre.
#place(top + left, dx: -1.5cm, rect(width: 21cm, height: 5.7cm, fill: rgb("#0b0b0d")))
#block(height: 5.7cm, inset: (x: 0pt, y: 0.9cm), {
  logo(28pt)
  v(13pt)
  block(width: 17.4cm, text(size: 23pt, weight: 600, tracking: -0.025em, hyphenate: false, fill: c.ink)[
    Comprar por volumen no debería \
    decidirse a ciegas.
  ])
  v(7pt)
  block(width: 15.8cm, text(size: 10pt, fill: c.soft)[
    APEX-EFN busca, filtra, negocia y contrasta cada oferta con la caja.
    La persona decide y firma.
  ])
  place(bottom + right, dx: -1.5cm, dy: -0.72cm, text(
    font: mono, size: 7.2pt, fill: c.muted, tracking: 0.04em,
  )[HACKFINANCE · MADRID ENGINEERING WEEK · 11 NOV 2026])
})

#v(0.55cm)

#let seccion(n, t, cuerpo) = block(width: 100%, breakable: false, {
  grid(
    columns: (0.82cm, 1fr), column-gutter: 6pt, align: horizon,
    box(fill: verde, inset: (x: 4pt, y: 2.5pt), text(size: 8pt, weight: 600, fill: white, n)),
    text(size: 15pt, weight: 600, fill: verde-oscuro, tracking: -0.01em, t),
  )
  v(3pt)
  line(length: 100%, stroke: 0.55pt + linea)
  v(5pt)
  cuerpo
  v(9pt)
})

#let problema(ico, t, d) = grid(
  columns: (0.62cm, 1fr), column-gutter: 4pt, align: top,
  icono(ico, verde, tam: 0.85em),
  {
    text(size: 9.5pt, weight: 600, t)
    linebreak()
    text(size: 8.4pt, fill: gris, d)
  },
)

#let paso(n, t, d) = grid(
  columns: (0.5cm, 1fr), column-gutter: 4pt, align: top,
  text(font: mono, size: 7.5pt, weight: 600, fill: verde, n),
  {
    text(size: 9pt, weight: 600, t)
    linebreak()
    text(size: 8.1pt, fill: gris, d)
  },
)

#let valor(ico, t, d) = block(
  width: 100%, fill: white, stroke: (left: 2.2pt + verde),
  inset: (x: 7pt, y: 6.5pt),
  {
    grid(
      columns: (0.45cm, 1fr), column-gutter: 4pt, align: horizon,
      icono(ico, verde, tam: 0.8em),
      text(size: 9pt, weight: 600, t),
    )
    v(2pt)
    text(size: 7.8pt, fill: gris, d)
  },
)

#let metrica(n, t) = block(
  width: 100%, fill: white, inset: 5pt,
  {
    text(size: 14pt, weight: 600, fill: verde-oscuro, tracking: -0.02em, n)
    linebreak()
    text(size: 7.2pt, fill: gris, t)
  },
)

#grid(
  columns: (10.6cm, 1fr), column-gutter: 0.5cm,
  {
    seccion("01", "El problema", [
      #problema("ban", [El precio real no está publicado], [Se negocia por chat, vendedor a vendedor, a menudo en otro idioma.])
      #v(5pt)
      #problema("shield-alert", [Lo más barato es lo más peligroso], [Precios gancho, falsificaciones y reseñas infladas.])
      #v(5pt)
      #problema("wallet", [El precio de lista no es el coste], [Faltan envío, aranceles, IVA de importación, divisa y coste de capital.])
      #v(5pt)
      #problema("history", [No hay prueba de la decisión], [Ni quién aprobó, ni con qué datos, ni si la caja lo aguantaba.])
    ])

    seccion("02", "La solución", [
      #text(size: 8.8pt, fill: gris)[
        APEX-EFN recorre el proceso completo. La IA busca y redacta; los números,
        las bandas y los límites los decide código determinista y versionado.
      ]
      #v(5pt)
      #paso("1", [Perfila], [Empresa, políticas y CSV financiero.])
      #v(3.5pt)
      #paso("2", [Busca], [Ofertas de varias plataformas.])
      #v(3.5pt)
      #paso("3", [Confía], [Score del vendedor, banda y versión del modelo.])
      #v(3.5pt)
      #paso("4", [Filtra el precio], [Mediana y MAD; lo anómalo no se negocia.])
      #v(3.5pt)
      #paso("5", [Negocia], [Chat con guardarraíles y aprobación humana.])
      #v(3.5pt)
      #paso("6", [Encaja], [Coste total contra presupuesto y tesorería.])
      #v(3.5pt)
      #paso("7", [Decide], [Dashboard con el porqué y las alternativas.])
      #v(3.5pt)
      #paso("8", [Firma], [Ed25519 en el navegador y ventana fija de 15 minutos.])
      #v(6pt)
      #block(width: 100%, fill: verde-suave, inset: 6pt, text(size: 7.5pt, fill: verde-oscuro)[
        Cada oferta viaja con su confianza, su banda de precio y su veredicto
        financiero. Ningún paso se salta.
      ])
    ])
  },
  {
    block(width: 100%, fill: verde-suave, inset: 8pt, {
      text(font: mono, size: 7.2pt, fill: verde, tracking: 0.06em)[VALOR DIFERENCIAL]
      v(5pt)
      valor("shield-check", [Confianza calculada], [Antigüedad, ventas, catálogo y reseñas. La manipulación capa la banda; el LLM no puntúa.])
      v(4pt)
      valor("ban", [Sanidad antes de negociar], [Un precio anómalo no consume ni una conversación. Barato y poco fiable escala a descarte.])
      v(4pt)
      valor("wallet", [Encaje real], [Coste total (envío, aranceles, IVA, FX, capital) contra presupuesto y tesorería.])
      v(4pt)
      valor("fingerprint", [Decisión demostrable], [Ed25519 en el navegador, cadena de hashes y WORM. Ventana fija de 15 min; doble control.])
      v(7pt)
      text(font: mono, size: 7.2pt, fill: verde, tracking: 0.06em)[EN NÚMEROS]
      v(3pt)
      grid(
        columns: (1fr, 1fr), row-gutter: 3pt, column-gutter: 3pt,
        metrica("8", "pasos del proceso"),
        metrica("3", "divisas EUR/USD/CNY"),
        metrica("15 min", "ventana de firma"),
        metrica("1.687+", "tests Python"),
      )
      v(7pt)
      text(font: mono, size: 7.2pt, fill: verde, tracking: 0.06em)[ESTADO]
      v(3pt)
      text(size: 7.8pt, fill: gris)[
        Onboarding y CSV, sourcing en dos plataformas mock, motores TS/Python,
        gate y dashboard, firma y negociación semiautomática. Siguiente:
        adaptadores reales y envío autónomo (F2).
      ]
      v(4pt)
      text(size: 7.2pt, fill: gris)[
        Infra local: RustFS con Object Lock COMPLIANCE. Producción: AWS S3.
      ]
    })
  },
)

#v(2pt)
#block(width: 100%, stroke: (top: 0.55pt + linea), inset: (y: 8pt), grid(
  columns: (1fr, 1fr, 1fr), column-gutter: 12pt,
  {
    text(size: 7pt, fill: gris)[*Comparadores*]
    linebreak()
    text(size: 7.2pt)[Precio de lista y reseñas sin tratar.]
  },
  {
    text(size: 7pt, fill: gris)[*Suites de compras*]
    linebreak()
    text(size: 7.2pt)[Proveedores ya homologados.]
  },
  {
    text(size: 7pt, fill: verde)[*APEX-EFN*]
    linebreak()
    text(size: 7.2pt)[Mercado abierto + riesgo + tesorería + firma.]
  },
))

#v(8pt)
#block(width: 100%, fill: verde-oscuro, inset: (x: 10pt, y: 7pt), {
  text(size: 10.5pt, weight: 600, fill: white)[
    La IA negocia. El código calcula. Una persona firma.
  ]
})
