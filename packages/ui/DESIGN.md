---
name: APEX-EFN
description: Sistema visual oscuro de APEX-EFN, plataforma B2B de compras por volumen donde un humano decide y firma. Neutros casi negros y esquinas rectas, con un único acento verde para lo interactivo y lo destacado; azul para lo bueno, amarillo para los avisos y rojo para lo malo; mezcla de la sobriedad de Vercel, la geometría recta de Render y las cifras grandes de la app de Revolut.
colors:
  background: "#0b0b0d"
  surface: "#131316"
  surface-raised: "#1b1b20"
  line: "#26262c"
  line-strong: "#36363e"
  control-border: "#6b6b77"
  ink: "#ededf0"
  ink-soft: "#b4b4be"
  ink-muted: "#8e8e9a"
  on-ink: "#0b0b0d"
  accent: "#8fbb8b"
  accent-hover: "#a0c99c"
  accent-subtle: "#16211a"
  accent-line: "#3a4a3b"
  on-accent: "#0b0b0d"
  success: "#5aa9ff"
  success-subtle: "#0d1f35"
  warning: "#e6c34a"
  warning-subtle: "#2a2308"
  danger: "#f7566a"
  danger-solid: "#c4271f"
  danger-solid-hover: "#cf2a22"
  danger-subtle: "#2e1117"
  white: "#ffffff"
  halo-1: "#8fbb8b"
  halo-2: "#5aa9ff"
  halo-3: "#a58bf0"
  halo-4: "#e07f9c"
typography:
  display:
    fontFamily: "Geist, sans-serif"
    fontSize: "clamp(2.25rem, 5vw, 3.5rem)"
    fontWeight: 600
    lineHeight: 1.05
    letterSpacing: "-0.03em"
    textWrap: "balance"
  numeral:
    fontFamily: "Geist, sans-serif"
    fontSize: "clamp(2rem, 4vw, 2.75rem)"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "-0.02em"
    fontFeature: "tnum"
  title:
    fontFamily: "Geist, sans-serif"
    fontSize: "28px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
    textWrap: "balance"
  headline:
    fontFamily: "Geist, sans-serif"
    fontSize: "22px"
    fontWeight: 600
    lineHeight: 1.25
    letterSpacing: "-0.015em"
    textWrap: "balance"
  heading:
    fontFamily: "Geist, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "-0.01em"
  body-long:
    fontFamily: "Geist, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.6
    textWrap: "pretty"
  body:
    fontFamily: "Geist, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Geist, sans-serif"
    fontSize: "14px"
    fontWeight: 500
    lineHeight: 1.4
  small:
    fontFamily: "Geist, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  mono:
    fontFamily: "Geist Mono, ui-monospace, monospace"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.45
  cjk-fallback:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, sans-serif"
    lineHeight: 1.7
rounded:
  none: "0px"
  dot: "50%"
spacing:
  unit: "4px"
  inline-gap: "8px"
  control-gap: "12px"
  group-gap: "24px"
  section: "48px"
  panel-padding: "24px"
  panel-padding-dense: "16px"
  row-height: "44px"
  row-height-dense: "36px"
  control-height: "36px"
  control-height-lg: "44px"
  header: "56px"
  sidebar: "240px"
  container: "1440px"
  prose: "68ch"
shadows:
  none: "none"
  overlay: "0 12px 32px rgba(0, 0, 0, 0.5)"
motion:
  press: "60ms"
  fast: "120ms"
  base: "180ms"
  overlay: "220ms"
  exit: "90ms"
  easing: "cubic-bezier(0.2, 0, 0, 1)"
  easing-move: "cubic-bezier(0.4, 0, 0.2, 1)"
shadcn:
  note: "Variables de shadcn/ui exportadas desde tweakcn. :root y .dark llevan los mismos valores (solo modo oscuro). Ojo: en shadcn 'accent' es el fondo de hover, no el color de marca; el color de marca es ring/chart-1."
  background: "{colors.background}"
  foreground: "{colors.ink}"
  card: "{colors.surface}"
  card-foreground: "{colors.ink}"
  popover: "{colors.surface}"
  popover-foreground: "{colors.ink}"
  primary: "{colors.accent}"
  primary-foreground: "{colors.on-accent}"
  secondary: "{colors.surface-raised}"
  secondary-foreground: "{colors.ink}"
  muted: "{colors.surface-raised}"
  muted-foreground: "{colors.ink-muted}"
  accent: "{colors.surface-raised}"
  accent-foreground: "{colors.ink}"
  destructive: "{colors.danger-solid}"
  destructive-foreground: "{colors.white}"
  border: "{colors.line}"
  input: "{colors.control-border}"
  ring: "{colors.accent}"
  chart-1: "{colors.accent}"
  chart-2: "{colors.ink-soft}"
  chart-3: "{colors.ink-muted}"
  chart-4: "{colors.line-strong}"
  chart-5: "{colors.line}"
  sidebar: "{colors.surface}"
  sidebar-foreground: "{colors.ink}"
  sidebar-primary: "{colors.accent}"
  sidebar-primary-foreground: "{colors.on-accent}"
  sidebar-accent: "{colors.surface-raised}"
  sidebar-accent-foreground: "{colors.ink}"
  sidebar-border: "{colors.line}"
  sidebar-ring: "{colors.accent}"
  radius: "0rem"
  font-sans: "Geist, sans-serif"
  font-mono: "Geist Mono, ui-monospace, monospace"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "{spacing.control-height}"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.control-border}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "{spacing.control-height}"
  button-secondary-hover:
    backgroundColor: "{colors.surface-raised}"
    borderColor: "{colors.ink-muted}"
  button-ghost:
    backgroundColor: "transparent"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.none}"
    padding: "0 10px"
    height: "{spacing.control-height}"
  button-ghost-hover:
    backgroundColor: "{colors.surface-raised}"
  button-destructive:
    backgroundColor: "{colors.danger-solid}"
    textColor: "{colors.white}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "{spacing.control-height}"
  button-destructive-hover:
    backgroundColor: "{colors.danger-solid-hover}"
  link:
    textColor: "{colors.accent}"
    textDecoration: "underline"
    underlineOffset: "3px"
  link-hover:
    textColor: "{colors.accent-hover}"
  focus-ring:
    outline: "2px solid {colors.accent}"
    outlineOffset: "2px"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.ink}"
    placeholderColor: "{colors.ink-muted}"
    borderColor: "{colors.control-border}"
    rounded: "{rounded.none}"
    padding: "0 12px"
    height: "{spacing.control-height}"
  input-focus:
    borderColor: "{colors.accent}"
  input-error:
    borderColor: "{colors.danger}"
  panel:
    backgroundColor: "{colors.surface}"
    borderColor: "{colors.line}"
    rounded: "{rounded.none}"
    padding: "{spacing.panel-padding}"
    shadow: "{shadows.none}"
  overlay:
    backgroundColor: "{colors.surface-raised}"
    borderColor: "{colors.line-strong}"
    rounded: "{rounded.none}"
    shadow: "{shadows.overlay}"
  table-header:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-muted}"
    typography: "{typography.small}"
    height: "{spacing.row-height-dense}"
  table-row:
    borderColor: "{colors.line}"
    height: "{spacing.row-height}"
  table-row-hover:
    backgroundColor: "{colors.surface-raised}"
  table-row-selected:
    backgroundColor: "{colors.accent-subtle}"
  badge-success:
    backgroundColor: "{colors.success-subtle}"
    textColor: "{colors.success}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    typography: "{typography.small}"
  badge-warning:
    backgroundColor: "{colors.warning-subtle}"
    textColor: "{colors.warning}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    typography: "{typography.small}"
  badge-danger:
    backgroundColor: "{colors.danger-subtle}"
    textColor: "{colors.danger}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    typography: "{typography.small}"
  badge-neutral:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-soft}"
    rounded: "{rounded.none}"
    padding: "2px 8px"
    typography: "{typography.small}"
  filter-chip:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-soft}"
    borderColor: "{colors.control-border}"
    rounded: "{rounded.none}"
    height: "32px"
  filter-chip-active:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.on-accent}"
  chat-halo:
    colors: "{colors.halo-1} · {colors.halo-2} · {colors.halo-3} · {colors.halo-4}"
    placement: "detrás del compositor, fuera del panel"
    states: "apagado en reposo · tenue con foco · intenso mientras piensa"
  dither:
    algorithm: "atkinson"
    dotShape: "{rounded.dot}"
    backgroundColor: "transparent"
    cellSize: "8px"
    dotDiameter: "5px"
    dotRamp: "{colors.background} → {colors.ink-muted}"
    dotLevels: 8
    dotTransition: "120ms"
    recomputeFps: 12
    rotationPeriod: "40s"
    revealDuration: "800ms"
  loader-spheres:
    count: 4
    fill: "{colors.ink}"
    shading: "none"
    sphereDiameter: "32px"
    gap: "12px"
    arcHeight: "0.31 × distancia"
    swapDuration: "650ms"
    bounceDuration: "420ms"
    bounceStagger: "90ms"
    bounceHeight: "16px"
    pause: "150ms"
    easing: "cubic-bezier(0.65, 0, 0.35, 1)"
  logo:
    source: "apps/web/public/brand/ (apex-isotipo.svg, apex-logo.css)"
    markViewBox: "0 0 64 40"
    markFill: "currentColor"
    markSize: "24px (cabecera) · 16px (mínimo) · 32px · 64px · 128px"
    wordmark: "apex"
    wordmarkFont: "Geist 600"
    wordmarkSize: "0.72 × ancho del isotipo"
    wordmarkTracking: "-0.04em"
    gap: "0.25 × ancho del isotipo"
    clearspace: "0.25 × ancho del isotipo"
    colorOnDark: "{colors.ink}"
    colorOnLight: "{colors.background}"
  language-switcher:
    backgroundColor: "transparent"
    backgroundColorHover: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    borderColor: "{colors.control-border}"
    borderColorOpen: "{colors.ink-muted}"
    rounded: "{rounded.none}"
    height: "38px"
    icon: "globe 16px, {colors.ink-soft}"
    code: "{typography.mono}, ES · EN · ZH"
    menuBackground: "{colors.surface-raised}"
    menuBorder: "{colors.line-strong}"
    menuWidth: "232px"
    itemHeight: "36px"
    itemHover: "{colors.line}"
---

# APEX-EFN — Sistema de diseño

> Ámbito: `apps/web/**` y `packages/ui/**` (carril DEV-6). El bloque YAML de arriba es la **fuente de
> verdad de los valores** (la clave `shadcn` mapea los tokens a las variables de shadcn/ui, tal como se
> generaron y validaron en tweakcn); este texto explica cómo usarlos. Si este documento contradice a
> `PROMPT-IMPLEMENTACION.md` en comportamiento de producto, gana el spec. Los tokens se implementan como
> variables CSS en `@theme` (Tailwind v4) en D6-01 y los componentes en D6-02.

## 1. Carácter

APEX-EFN es una herramienta donde alguien **firma compras con dinero real**. Tiene que parecer un
instrumento preciso, no una demo.

- **Vercel:** neutros sobre casi negro, tipografía Geist, bordes finos, cero adorno.
- **Render:** esquinas rectas (radio 0 en todo) y bordes de 1 px.
- **Un solo acento:** el verde `accent` es para lo interactivo y lo destacado (foco, selección, enlaces,
  botón principal, serie principal). Relleno = se pulsa; línea o barra = solo señala. El resto del color es
  de estado: azul bueno, amarillo atención y rojo malo, y cuando aparece significa algo.
- **Revolut app:** cifras grandes y seguras (`numeral`), paneles amplios, la cantidad como protagonista.

Solo modo oscuro. No hay tema claro: un único tema evita mantener dos paletas y que una de las dos quede descuidada.

## 2. Lo que no hacemos

Patrones que hacen que una interfaz parezca generada y que este sistema excluye:

- Modo claro o un segundo tema. APEX-EFN es solo oscuro.
- Negro puro (`#000`) de fondo o blanco puro para texto: cansan la vista y hacen vibrar el contraste.
- Brillos radiales detrás del hero, tarjetas con degradado, glassmorphism, sombras de color. Única
  excepción: el halo del compositor de los chats (§6), solo ahí y sin efecto cristal.
- Titulares que entran con desenfoque.
- Esquinas redondeadas en la interfaz: todo es recto (`rounded.none`). Lo único circular son los puntos
  del dithering.
- Una paleta paralela de grises o tonos casi iguales definidos elemento a elemento. Todo gris sale de
  `colors` del YAML.
- Texto de 9–12 px. El mínimo es `small` (13 px).
- Etiquetas en mayúsculas espaciadas encima de un titular («eyebrows»), en píldora o sin ella.
- Bloques de CSS que sobrescriben reglas anteriores en lugar de cambiarlas.
- Titulares a dos tonos (primera línea oscura, segunda gris).
- Iconos decorativos inventados (cubos apilados, destellos) y flechas de adorno. Las únicas flechas son las
  de enlace, las de fila (`ArrowUpRight`), las de orden de columna y las de tendencia (§6).
- Rejillas de tarjetas idénticas con icono + título + frase.
- Inventar cifras, clientes, logos, testimonios, premios o fotos. Si no hay dato real, no se muestra.

## 3. Reglas para quitar el aspecto «generado»

Aplican a todo componente y pantalla. Se revisan en cada PR (§13).

1. **Sin badges de relleno.** Nada de «Nuevo», «IA», «Beta», ni badges que repitan algo ya visible. Un
   badge solo existe si comunica un estado de dominio (§6).
2. **Sin etiquetas redundantes.** Un importe con divisa, una fecha o un nombre de vendedor no necesitan
   rótulo encima.
3. **Sin cursivas al azar.** Nunca se resalta una palabra suelta con cursiva o color.
4. **Mono solo donde hace falta.** `mono` es para IDs, hashes, claves públicas y código. Nunca para
   cifras, titulares ni etiquetas «técnicas».
5. **Sistema de diseño siempre.** Solo componentes de `@apex/ui` y tokens de este archivo.
6. **Mostrar el producto real.** Pantallas, capturas y stories con datos reales del contrato (fixtures),
   no textos de relleno.
7. **Agrandar lo principal.** Un elemento dominante por vista (el precio, la decisión, el KPI con
   `numeral`); todo lo demás baja de nivel.
8. **Agrupar con espacio, no con cajas.** Elementos relacionados a `inline-gap`/`control-gap`; grupos
   separados por `group-gap`; secciones por `section`. No añadir bordes o paneles para agrupar.
9. **Titulares concretos.** «3 ofertas esperan tu firma», no «Compras inteligentes, simplificadas».
10. **Destacar el CTA.** Un solo `button-primary` por zona; el resto `secondary` o `ghost`.
11. **Un solo acento.** Foco, selección, enlaces, botón principal y serie principal usan `accent` (verde).
    Relleno = se pulsa; línea o barra = solo señala. Los enlaces además van subrayados. Los colores de estado
    no son acentos: solo significan estado, y el amarillo nunca marca algo activo.
12. **Iconos en todas las acciones.** Solo lucide, mismo trazo (1.75) y tamaño (16 px en texto, 20 px en
    navegación). Llevan icono la navegación, todas las acciones, los badges, las cabeceras de sección, los
    estados vacíos, los errores y el chat; las cabeceras de columna, donde ayude.
13. **Quitar adornos.** Si algo se puede eliminar sin perder información, se elimina.
14. **Radio 0.** Paneles, botones, inputs, badges, chips y diálogos con esquinas rectas. La jerarquía la
    dan el borde y el paso de luminosidad, no la forma.
15. **Contraste de texto alto.** `ink` para texto principal, `ink-soft` para secundario, `ink-muted` como
    mínimo (≥ 5.3:1 sobre cualquier superficie). Nunca grises más oscuros para texto.
16. **Titulares bien partidos.** `text-wrap: balance` en titulares, `pretty` en párrafos; sin viudas.
17. **Alinear a ojo, no a píxel.** Ajustar ópticamente iconos junto a texto, triángulos de «play»,
    cifras grandes con su divisa.
18. **Cifras tabulares.** Todo número comparable usa `tabular-nums` y va alineado a la derecha en tablas.
19. **Estados de carga.** Toda vista asíncrona tiene carga (skeleton con la forma final), vacío, error y
    datos. **Siempre**, cualquier componente que cargue al arrancar una página usa un skeleton, nunca
    `SphereLoader`, un spinner ni una pantalla en blanco.
20. **Todo lo interactivo responde.** La respuesta es del tamaño justo según el presupuesto por frecuencia
    (§8): cuanto más se usa algo, menos se anima. Si se quita una animación y no se pierde significado, se borra.

## 4. Color

- Todo color se consume por token semántico (`bg-surface`, `text-ink-muted`, `border-line`…). Prohibidos
  hex literales, paleta cruda de Tailwind (`bg-red-100`) y valores arbitrarios en componentes.
- Jerarquía de superficie: en oscuro, **más elevado = más claro**. `background` (página e inputs) →
  `surface` (paneles) → `surface-raised` (cabeceras de tabla, hover, popovers, badge neutro). Las capas se
  separan con `line` y con ese paso de luminosidad, no con sombra.
- El botón principal es `accent` con texto `on-accent` y hover `accent-hover`; el destructivo usa `danger-solid` con texto
  `white`. `danger` (más claro) es solo para texto e iconos de error.
- Los fondos `*-subtle` son tintes muy oscuros: en badges el texto va en el color de estado, nunca en blanco.
- `control-border` para el borde de los controles interactivos (inputs, selects, botón secundario, chips): da
  el 3:1 que pide WCAG 1.4.11. `line-strong` queda para divisores fuertes y el borde de las capas flotantes.
- El color nunca es la única señal: todo estado es **icono + color + texto**. Fuera de los conceptos de
  dominio (§6), que tienen su icono propio:

| Significado | Token | Icono lucide |
|---|---|---|
| Bueno | `success` (azul) | `CircleCheck` |
| Atención | `warning` (amarillo) | `TriangleAlert` |
| Malo | `danger` (rojo) | `OctagonAlert` |
| Sin datos / neutro | `ink-soft` (gris) | `CircleHelp` |

## 5. Tipografía

- Geist para todo; Geist Mono según la regla 4; `cjk-fallback` para `zh` (con interlineado 1.7 y sin
  cursivas).
- Por defecto la app usa `body` (14 px). `body-long` (16 px) para texto corrido: explicaciones,
  transcript de negociación. Máximo `prose` de ancho.
- `display` solo en login/landing. `numeral` para el importe o KPI protagonista de una vista.
- Pesos: 400, 500 y 600. Nada más.
- Mayúscula solo inicial en títulos y botones.

## 6. Componentes de dominio

La UI **muestra, no calcula**: importes, bandas, puntuaciones y elegibilidad vienen de la API.

| Concepto | Valor | Badge | Icono lucide |
|---|---|---|---|
| Confianza vendedor | `high` | success | `ShieldCheck` |
| | `medium` | neutral | `Shield` |
| | `low` | warning | `ShieldAlert` |
| | `untrusted` | danger | `ShieldX` |
| | `insufficient_data` | neutral | `ShieldQuestion` |
| Banda de precio | `normal` | success | `CircleCheck` |
| | `atypical` | warning | `TriangleAlert` |
| | `implausible` | danger | `OctagonAlert` |
| | `insufficient_reference` | neutral | `CircleHelp` |
| Veredicto financiero | `within_budget` | success | `Wallet` |
| | `stretch` | warning | `WalletMinimal` |
| | `out_of_budget` | danger | `Ban` |
| Firma | `signed` | success | `BadgeCheck` |
| | `pending` | neutral | `Clock` |
| | `invalid` | danger | `BadgeAlert` |
| Avisos | `fx_provisional`, `financials_stale` | warning | `Info`, `History` |

- **Fila de oferta:** `precio · banda de precio · confianza · veredicto · firma`, siempre en ese orden y
  siempre visibles en la tabla.
- Cada badge abre un popover con el porqué (desglose de señales y `model_version`; mediana de
  referencia y muestra; razones numéricas; firmante, hora y hash en `mono`).
- **`MoneyDisplay`:** recibe `{amount_minor, currency}` y formatea con `Intl.NumberFormat`. Sin sumas ni
  redondeos. Signo menos real (`−`). Importe convertido: el original en tooltip.
- **Botones deshabilitados** muestran la razón que devuelve la API (tooltip accesible con
  `aria-describedby`). Las acciones que firman llevan icono `PenLine` y texto «Firmar…».
- **`SigningSessionIndicator`** en la cabecera: firmante, `mm:ss`, firmas restantes. En los últimos 60 s
  pasa a `warning` sin parpadear; al expirar, la vista queda en solo lectura con «Reautenticar para firmar».
- **Tablas:** cabecera `table-header` fija, divisores solo horizontales, números a la derecha, fila
  seleccionada `table-row-selected`, paginación «Cargar más» (cursor). El título de la fila es un enlace real
  (`<a>`, funciona con teclado y Ctrl+clic) con `ArrowUpRight` que aparece en hover; no hay columna «Abrir».
- **Flechas de tendencia:** la dirección dice cómo se mueve el valor y el color dice si eso es bueno. Un precio
  que baja es bueno (`ArrowDown` en `success`); uno que sube es malo (`ArrowUp` en `danger`). La capacidad de
  compra funciona al revés. Siempre con la cifra al lado (`ArrowDown −4,9 %`).
- **Chat (`UiChat`):** una sola pieza para Nueva misión y Negociación. En reposo, compositor compacto de una
  línea; al hacer clic crece hacia arriba en `motion.overlay`, sin rebote. Panel opaco y radio 0, sin
  glassmorfismo. El halo (`chat-halo`) es una sombra difusa detrás del compositor, **fuera del panel** y nunca
  detrás de cifras, con cuatro colores que rotan despacio: apagado en reposo, tenue con foco, intenso mientras
  piensa. Es la única excepción decorativa del sistema y no se usa fuera de los chats. Se detiene con
  movimiento reducido o con la pestaña oculta.
- **Formularios:** etiqueta encima, ayuda y error debajo en `small`. Validación al salir del campo y al
  enviar. Importes en input de texto decimal con divisa explícita, nunca `type="number"`.
- **Estados:** skeleton con la forma final; vacío con un icono, un título concreto y una acción; error con
  el `title`/`detail` de problem+json y «Reintentar». `428 reauth_required` abre el flujo de passkey, no
  muestra error.
- **Gráficas (Recharts):** serie principal `accent`, el resto en grises de `ink-muted`/`line-strong`;
  bandas de sanity como áreas `warning-subtle`/`danger-subtle`; sin degradados ni 3D; tabla alternativa
  para lectores de pantalla.

## 7. Layout

- Cabecera de `header`, barra lateral de `sidebar` (colapsable a 64 px), contenido hasta `container` con
  padding lateral de 24 px.
- Escritorio primero (uso profesional), pero ninguna vista se rompe a 360 px.
- Densidad: `row-height` por defecto, `row-height-dense` en comparativas, elegida por prop.
- En oscuro la sombra apenas se ve: las capas flotantes (`overlay`) se distinguen por `surface-raised` +
  `line-strong` y una sombra negra difusa. Paneles con borde y sin sombra.

## 8. Movimiento

**Se mueven las líneas, no las cajas.** APEX es un instrumento con esquinas rectas y bordes de 1 px: lo que
responde son bordes, reglas e indicadores. Los paneles y botones no flotan ni rebotan. La única caja que cambia
de tamaño es el compositor del chat (§6), porque ahí se pasa de mirar a escribir.

**Presupuesto según la frecuencia.** Cuanto más se usa algo, menos se anima.

| Nivel | Frecuencia | Qué pasa |
|---|---|---|
| 0 · Inmediato | Cientos de veces al día o por teclado: hover de fila, opciones de menú, foco, atajos | Entra en 0 ms; al salir, se apaga en `motion.fast` |
| 1 · Respuesta | Decenas al día: botones, inputs, tabs, checkbox | Un solo cambio de 60–120 ms (`motion.press`, `motion.fast`) |
| 2 · Transición | Abrir o cerrar capas, expandir el chat | 120–220 ms (`motion.fast` a `motion.overlay`); el cierre, más rápido que la apertura (`motion.exit`) |
| 3 · Momento | Registrar una firma | 600 ms; es el único |

`motion.base` es para los cambios de estado. `motion.easing` para las entradas y `motion.easing-move` para lo
que se desplaza en pantalla.

Respuesta por componente:

| Componente | Respuesta |
|---|---|
| Botón primario | Hover: cambio de tono. Pulsado: baja 1 px como una tecla, sin escalar, y vuelve en `fast` |
| Botón secundario | El borde sube a `ink-muted` |
| Botón ghost | Aparece el fondo; el icono no se mueve |
| Botón ocupado | Mantiene el ancho; `ShiningText` en el texto y sin spinner |
| Dropdown | El panel se revela como una persiana desde el borde del control (`clip-path`, `fast`); cierre con opacidad en `exit`; el chevron gira |
| Opción de menú | Nivel 0 |
| Input / textarea | El borde pasa a acento en `press`; el foco, al instante |
| Checkbox / radio | Relleno inmediato y el check aparece con recorte en `fast` |
| Switch | El mando se desplaza en `fast` con `easing-move`, sin rebote |
| Tabs de una vista | El indicador de 2 px **viaja** a la pestaña nueva; es la línea que se mueve |
| Navegación principal | Sin viaje: cambia de página |
| Fila de tabla | Nivel 0. Entra una regla interior de 1 px en acento; `ArrowUpRight` aparece por opacidad |
| Ordenar columna | La flecha gira; las filas cambian sin animación |
| Badge que cambia | Cruce de color en `base`, sin pulso |
| Fila nueva o recalculada | Tinte `accent-subtle` que se apaga en 1,2 s |
| Tooltip | 500 ms de espera la primera vez, inmediato al pasar al siguiente; 100 ms de opacidad |
| Diálogo | Fondo en `fast`; panel con opacidad y 4 px en `overlay`; cierre en `exit`, sin escala |
| Toast | Entra desde el borde en `base`, sin barra de tiempo; se pausa con hover |
| Cifras | Cruce de 120 ms con `tabular-nums`. Nunca un valor intermedio |
| Cuenta atrás | Sin animación; último minuto en aviso, sin parpadeo |
| Skeleton | Opacidad .6–1 en 1,6 s |

**El único momento coreografiado: registrar una firma.** Al confirmar, una línea de 1 px recorre la fila de
izquierda a derecha, dejando tras ella el estado `Firmado`; después, el hash se revela con un recorte en `mono`.
600 ms en total, una vez. Con movimiento reducido, cambio de estado directo.

**Descartado:**

- Barrido de luz en botones, brillo en hover, botones que se elevan: es la plantilla de landing generada.
- Rebote o `spring` con sobrepaso: aquí se firma dinero.
- Opciones de menú y listas escalonadas: retrasan justo lo que se va a pulsar.
- Contadores que suben hasta la cifra: muestran importes falsos durante la animación.
- Filas que se recolocan al ordenar: impiden leer mientras se compara.
- Texto palabra a palabra con cursor parpadeante: la respuesta real llega a trozos.
- Mantener pulsado para firmar con relleno: fricción falsa, la firma ya exige sesión y passkey.
- Foco animado: el foco se ve al instante.
- Skeleton con brillo que recorre: se usa una opacidad lenta y discreta.
- Barra de tiempo en toasts y checks dibujados en cada botón: adorno repetido.
- `transition: all`, entradas de página o al hacer scroll, desenfoques y parallax: sin función.

**Implementación:** transiciones CSS, que se pueden interrumpir, antes que keyframes; propiedades siempre
enumeradas; hover solo dentro de `@media (hover: hover)`.

- Los bucles solo existen en el campo de puntos (§9), el indicador de carga (§9.2), `ShiningText`, la opacidad
  del skeleton y el halo del chat (§6).
- **`ShiningText`:** un brillo que recorre el texto en bucle (2 s, lineal), de `ink-muted` a `ink`. Solo
  para trabajo que un agente está haciendo **ahora**: «Redactando la contraoferta…», «Buscando ofertas…»,
  «Analizando el CSV…». Nunca en títulos, cifras o estados terminados. Lleva `role="status"`; con reduced
  motion queda estático en `ink-muted`.
- `prefers-reduced-motion`: sin desplazamientos; se mantienen el color y la opacidad que comunican estado.

## 9. Campo de puntos y carga

Único recurso gráfico del sistema. Dos componentes: `DotField` (token `components.dither`) y `SphereLoader`
(token `components.loader-spheres`).

### 9.1 Campo de puntos (`DotField`)

- **Rejilla:** toda la zona es una rejilla regular de `cellSize`; cada celda es un **círculo** de diámetro
  fijo (`dotDiameter`). Nada de cuadrados ni `image-rendering: pixelated`.
- **Atkinson:** la imagen fuente se convierte a 1 bit con difusión de error Atkinson (6/8 del error a seis
  vecinos, umbral 0.5). El algoritmo puede cambiar si visualmente no convence.
- **Los puntos cambian de intensidad, no de tamaño.** Al encenderse o apagarse, cada punto recorre una
  rampa de grises (`dotRamp`, en `dotLevels` pasos) en `dotTransition`. Escalar el radio deforma la
  rejilla y se lee como «burbujeo»; la intensidad mantiene la retícula intacta.
- **Estabilidad:** Atkinson reordena muchos puntos ante cambios pequeños, así que el patrón se recalcula a
  `recomputeFps` y la transición de intensidad suaviza el resto.
- **Motivo (pendiente de elegir):** hay tres candidatos en el lienzo "APEX wireframes", todos con puntos
  circulares que solo cambian de intensidad:
  1. **Autómata celular elemental, regla 30**, sembrado con una sola celda, en rejilla cuadrada de 8 px. La
     generación nueva entra por arriba y las filas antiguas pierden intensidad hacia abajo. Es binario, así que
     no pasa por Atkinson: el gris sale de la edad de la fila.
  2. **Reacción-difusión Gray-Scott** en rejilla **hexagonal** (filas desplazadas medio paso, laplaciano de
     seis vecinos), celda de 7 px. Da un patrón de laberinto que deriva despacio; el gris sale de la
     concentración.
  3. **Manchas de jirafa:** distancia entre las dos semillas Worley más cercanas (F2 − F1) con deformación
     suave, en rejilla hexagonal de 10 px y puntos de 7,8 px. Los bordes entre manchas quedan vacíos y las
     semillas se desplazan lentamente.
  Al elegir uno se borran los otros dos de este documento y se ajustan `cellSize` y `dotDiameter`.
- **Animaciones** acordadas, independientes del motivo:
  1. **Revelado al cargar**, una vez, en `revealDuration`.
  2. **Estado del sistema:** más movimiento mientras algo trabaja; una onda al terminar con éxito.
  3. **Bucle lento** del motivo, en `rotationPeriod`.
  4. **Reacción al CTA:** el campo responde al hover o foco del botón principal.
- `prefers-reduced-motion`: un único fotograma estático. `aria-hidden`, `pointer-events: none`.
- **Dónde:** de momento solo en el login. Nunca detrás de importes, tablas o el gate.

### 9.2 Indicador de carga (`SphereLoader`)

- Cuatro bolas **lisas, blancas (`ink`) e idénticas**, sin sombreado ni dithering, en línea horizontal.
- Se intercambian por parejas contiguas: una viaja por un **arco por encima** y la otra por un **arco por
  debajo**, como las transiciones de un autómata finito. La altura del arco es proporcional a la distancia.
- **Alterna dos movimientos:** un intercambio y después una **ola**: las cuatro bolas botan una tras otra de
  izquierda a derecha (`bounceDuration`, desfase `bounceStagger`, altura `bounceHeight`, trayectoria
  parabólica). Pausa `pause` entre movimientos. Las parejas de intercambio rotan: 1–2, 3–4, 2–3.
- Uso: modales de carga y esperas de más de 400 ms. Siempre con texto que diga qué se espera
  («Firmando decisión…») y `role="status"`. Con reduced motion: bolas quietas y el texto.
- No es para la carga inicial de una página: cualquier componente que cargue al arrancar la página usa
  siempre un skeleton con la forma final (regla 19).

## 10. Logo

El logo vive en `apps/web/public/brand/` (`apex-isotipo.svg`, `apex-icono.svg`, `apex-logo.css`, y la hoja
de marca en `index.html`). Es la única forma de escribir el nombre del producto en la interfaz: nunca
«APEX» o «APEX-EFN» en texto plano como marca, ni el nombre antiguo TRATO.

- **Isotipo:** hexágono achatado con un pico en negativo, retícula 64 × 40. Un solo color
  (`currentColor`), esquinas rectas, sin degradados ni sombras.
- **Logotipo:** isotipo a la izquierda y «apex» en minúsculas, Geist 600, tracking −0,04 em. El texto mide
  el 72 % del ancho del isotipo y la separación es un cuarto de ese ancho. Nunca en otra fuente ni en mayúsculas.
- **Tamaños:** `--apex-mark-size` es el ancho del isotipo. 24 px en la cabecera de la app (56 px de alto),
  16 px como mínimo para el isotipo solo; 32/64/128 px para login, documentos y la hoja de marca.
- **Color:** `ink` sobre `background`/`surface`; `background` sobre claro (PDF, impresión). `ink-soft` solo
  en contextos secundarios (pie, documentos).
- **Área de seguridad:** un cuarto del ancho del isotipo por cada lado. Nada (nav, badges) dentro de ella.
- **Dónde va:** primer elemento de `AppHeader` y de la cabecera del onboarding, enlazando a Decisiones;
  arriba a la izquierda del login, sin enlace. Accesible como «APEX» (`aria-label`), el isotipo `aria-hidden`.
- **Implementación:** componente `Logo` en `@apex/ui` con `size` (`sm`, `md`, `lg`, `xl`) y `tone`
  (`onDark`, `onLight`, `soft`); SVG en línea con `fill="currentColor"` o la máscara de `apex-logo.css`.
  Favicon: `apex-icono.svg`.

## 11. Accesibilidad e internacionalización

- WCAG 2.2 AA. Foco siempre visible con `focus-ring`; nunca `outline: none` sin sustituto.
- Objetivo táctil mínimo 24×24 px; 32 px en acciones de fila.
- `axe` en Storybook y Playwright; violaciones `serious`/`critical` bloquean el PR.
- Todo texto por `next-intl` (`es`, `en`, `zh`). Sin anchos fijos en botones o etiquetas: el español
  crece un 20–30 % respecto al inglés.
- Números, divisas y fechas con el locale activo vía `Intl`. Fechas relativas siempre con tooltip absoluto.
- **Selector de idioma** (`LanguageSwitcher`, token `language-switcher`): en la cabecera, a la izquierda del
  indicador de firma; en onboarding y login, arriba a la derecha. Botón con icono de globo, el código del
  idioma activo en mono (`ES`, `EN`, `ZH`) y un chevron; nunca banderas (un idioma no es un país). Abre un
  menú con el título «Idioma de la interfaz» y cada idioma por su endónimo (Español, English, 简体中文),
  con su código a la derecha y un check en el activo. Cada opción lleva su `lang` (`es`, `en`, `zh-Hans`)
  para que se lea y pronuncie bien. `aria-haspopup="menu"`, `aria-expanded`, opciones `menuitemradio`,
  Escape y clic fuera cierran. Cambiar de idioma no recarga ni pierde contexto: cambia el locale de
  next-intl, guarda la preferencia del usuario y mantiene la ruta.

## 12. Código

- Tailwind v4 CSS-first: los tokens del YAML se declaran una vez en `@theme`
  (`apps/web/src/styles/globals.css`) y se reexportan en `packages/ui/src/styles.css` para Storybook.
- Variantes con `cva`, combinación con `cn()`. Sin `style={{}}` para color o espaciado, sin
  `!important`, sin CSS modules nuevos.
- Se cambia la regla existente; nunca se añade un bloque posterior que la sobrescriba.
- Cada componente de `packages/ui` llega con story (variantes, `es` y `zh`, datos reales) y test de axe.

### Prompt base para agentes que tocan UI

```text
Eres DEV-6. Construye <componente/vista> para APEX-EFN siguiendo packages/ui/DESIGN.md al pie de la letra:
los valores del YAML son los únicos permitidos y las secciones 2 y 3 son obligatorias. Solo modo oscuro.
Usa componentes de @apex/ui, iconos lucide y textos vía next-intl (es/en/zh). La UI no calcula dinero ni
bandas: muestra lo que devuelve la API. Usa datos reales de los fixtures del contrato.
Implementa carga/vacío/error/datos. Entrega componente + story + test axe. Después renderiza, haz una
captura con Playwright, revísala contra la checklist de la sección 13 y corrige lo que falle antes de
terminar. Indica qué reglas comprobaste.
```

### Componentes del lienzo

El lienzo de wireframes ya separa las piezas comunes en componentes que importan todas las pantallas. Son el
borrador de los componentes de `@apex/ui` y deben implementarse con el mismo nombre de concepto:

| Lienzo | `@apex/ui` | Notas |
|---|---|---|
| `UiCabecera` | `AppHeader` | navegación primaria de `apps/web/NAVIGATION.md` §4 |
| `UiChipFirma` | `SigningSessionIndicator` | estados activa, caduca pronto, caducada, sin firmas, sin sesión |
| `UiEmpresaNav` | `CompanyNav` | subnavegación de Empresa |
| `UiBoton` | `Button` | variantes `pri`, `sec`, `ghost`, `danger`; tamaños `sm`, `md`, `lg`; deshabilitado con motivo |
| `UiBadge` | `StatusBadge` | tonos `ok`, `warn`, `bad`, `neutro`, `plano`; la forma del punto distingue el tono además del color |
| `UiCargando` | `SphereLoader` | §9.2 |
| `UiLogo` | `Logo` | §10; tamaños `sm`, `md`, `lg`; tonos `claro`, `oscuro`, `suave` |
| `UiIdioma` | `LanguageSwitcher` | §11; `es`, `en`, `zh` |

La navegación entre pantallas, las guardas y el inventario de modales están en `apps/web/NAVIGATION.md`.

## 13. Checklist de PR

- [ ] Solo tokens de este archivo; ningún gris, color, radio o tamaño fuera del YAML.
- [ ] Nada de la sección 2 (tema claro, degradados, eyebrows, titulares a dos tonos, rejillas de tarjetas…); halo solo en el compositor de los chats.
- [ ] `accent` solo en lo interactivo y lo destacado; relleno = se pulsa, línea o barra = solo señala.
- [ ] Controles interactivos con borde `control-border`; estados con icono + color + texto (azul, amarillo, rojo, gris).
- [ ] Iconos lucide en todas las acciones; flechas de tendencia con la cifra al lado.
- [ ] Título de fila como enlace real, sin columna «Abrir».
- [ ] Sin badges de relleno ni etiquetas redundantes; mono solo en IDs/hashes.
- [ ] Un elemento dominante y un único CTA primario por zona; titular concreto y con `balance`.
- [ ] Radio 0 en todos los elementos de interfaz.
- [ ] La marca es el logo de `apps/web/public/brand/` (§10), nunca el nombre en texto plano.
- [ ] Texto ≥ 13 px y contraste ≥ `ink-muted`.
- [ ] Cifras tabulares a la derecha; dinero solo con `MoneyDisplay`.
- [ ] Confianza y banda de precio junto al precio; firma junto al trato.
- [ ] Botones deshabilitados con razón visible.
- [ ] Carga, vacío, error y datos implementados; componentes de carga inicial con skeleton; movimiento dentro del presupuesto de §8, sin nada de su lista de descartes.
- [ ] Textos en `es`/`en`/`zh`, probado con textos largos; `axe` limpio; foco visible.
