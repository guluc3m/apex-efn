// Tokens y componentes de packages/ui/DESIGN.md, en Typst.
#let c = (
  bg: rgb("#0b0b0d"),
  panel: rgb("#131316"),
  raised: rgb("#1b1b20"),
  line: rgb("#26262c"),
  line-strong: rgb("#36363e"),
  control: rgb("#6b6b77"),
  ink: rgb("#ededf0"),
  soft: rgb("#b4b4be"),
  muted: rgb("#8e8e9a"),
  accent: rgb("#8fbb8b"),
  accent-subtle: rgb("#16211a"),
  accent-line: rgb("#3a4a3b"),
  good: rgb("#5aa9ff"),
  good-subtle: rgb("#0d1f35"),
  warn: rgb("#e6c34a"),
  warn-subtle: rgb("#2a2308"),
  bad: rgb("#f7566a"),
  bad-subtle: rgb("#2e1117"),
)
#let fuente = "Geist"
#let mono = "Geist Mono"

// Logotipo de apps/web/public/brand/apex-logo.css: `w` es el ancho del isotipo.
// tono "claro" va sobre oscuro; "oscuro" sobre claro.
#let logo(w, tono: "claro") = box(grid(
  columns: 2, column-gutter: w * 0.25, align: horizon,
  image("/apps/web/public/brand/apex-isotipo-" + tono + ".svg", width: w),
  move(dy: -0.03 * w, text(
    font: fuente, weight: 600, size: w * 0.72, tracking: -0.04em,
    fill: if tono == "claro" { c.ink } else { c.bg }, "apex",
  )),
))

#let icono(nombre, color, tam: 1.1em) = box(baseline: 0.17em, image(
  bytes(read("iconos/" + nombre + ".svg").replace("currentColor", color.to-hex())),
  format: "svg", width: tam,
))

// Badge de packages/ui/src/components/badge.tsx: estado = icono + color + texto.
#let tonos = (
  ok: (c.good-subtle, c.good, "circle-check"),
  warn: (c.warn-subtle, c.warn, none),
  bad: (c.bad-subtle, c.bad, "octagon-alert"),
  neutro: (c.raised, c.soft, "circle-help"),
  plano: (c.raised, c.soft, none),
)
#let badge(t, tono: "neutro", ico: none) = {
  let (fondo, color, base) = tonos.at(tono)
  let g = if ico != none { ico } else { base }
  box(fill: fondo, inset: (x: 0.6em, y: 0.26em), text(fill: color, {
    if g != none { icono(g, color); h(0.4em) } else if tono == "warn" {
      box(polygon(fill: color, (0.32em, 0em), (0.64em, 0.6em), (0em, 0.6em)))
      h(0.4em)
    }
    t
  }))
}

#let comparativa = (
  ("Negocia en el chat", "No", "Proveedores homologados", "En marketplaces abiertos"),
  ("Confianza del vendedor", "Reseñas en bruto", "Proveedor ya validado", "Calculada y versionada"),
  ("Precios anómalos", "Los muestra primero", "Fuera de su alcance", "Filtrados antes de negociar"),
  ("¿Se puede pagar?", "No lo sabe", "Vía ERP", "Contra su tesorería real"),
  ("Rastro de la decisión", "Ninguno", "Flujo de aprobación", "Firma Ed25519 encadenada"),
)
