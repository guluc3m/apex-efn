---
name: TRATO
description: Sistema visual oscuro de TRATO, plataforma B2B de compras por volumen donde un humano decide y firma. Monocromo puro y esquinas rectas, sin color de acento; mezcla de la sobriedad de Vercel, la geometría recta de Render y las cifras grandes de la app de Revolut.
colors:
  background: "#0b0b0d"
  surface: "#131316"
  surface-raised: "#1b1b20"
  line: "#26262c"
  line-strong: "#36363e"
  ink: "#ededf0"
  ink-soft: "#b4b4be"
  ink-muted: "#8e8e9a"
  on-ink: "#0b0b0d"
  accent: "#ededf0"
  accent-deep: "#ffffff"
  accent-subtle: "#1b1b20"
  on-accent: "#0b0b0d"
  success: "#3fbf74"
  success-subtle: "#0f2419"
  warning: "#f5873a"
  warning-subtle: "#2d1a0b"
  danger: "#f7566a"
  danger-solid: "#c4271f"
  danger-solid-hover: "#a31f18"
  danger-subtle: "#2e1117"
  white: "#ffffff"
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
  fast: "120ms"
  base: "180ms"
  overlay: "220ms"
  easing: "cubic-bezier(0.2, 0, 0, 1)"
shadcn:
  note: "Variables de shadcn/ui exportadas desde tweakcn. :root y .dark llevan los mismos valores (solo modo oscuro). Ojo: en shadcn 'accent' es el fondo de hover, no el color de marca; el color de marca es ring/chart-1."
  background: "{colors.background}"
  foreground: "{colors.ink}"
  card: "{colors.surface}"
  card-foreground: "{colors.ink}"
  popover: "{colors.surface}"
  popover-foreground: "{colors.ink}"
  primary: "{colors.ink}"
  primary-foreground: "{colors.on-ink}"
  secondary: "{colors.surface-raised}"
  secondary-foreground: "{colors.ink}"
  muted: "{colors.surface-raised}"
  muted-foreground: "{colors.ink-muted}"
  accent: "{colors.surface-raised}"
  accent-foreground: "{colors.ink}"
  destructive: "{colors.danger-solid}"
  destructive-foreground: "{colors.white}"
  border: "{colors.line}"
  input: "{colors.line-strong}"
  ring: "{colors.accent}"
  chart-1: "{colors.accent}"
  chart-2: "{colors.ink-soft}"
  chart-3: "{colors.ink-muted}"
  chart-4: "{colors.line-strong}"
  chart-5: "{colors.line}"
  sidebar: "{colors.surface}"
  sidebar-foreground: "{colors.ink}"
  sidebar-primary: "{colors.ink}"
  sidebar-primary-foreground: "{colors.on-ink}"
  sidebar-accent: "{colors.surface-raised}"
  sidebar-accent-foreground: "{colors.ink}"
  sidebar-border: "{colors.line}"
  sidebar-ring: "{colors.accent}"
  radius: "0rem"
  font-sans: "Geist, sans-serif"
  font-mono: "Geist Mono, ui-monospace, monospace"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "{spacing.control-height}"
    typography: "{typography.label}"
  button-primary-hover:
    backgroundColor: "{colors.ink-soft}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    borderColor: "{colors.line-strong}"
    rounded: "{rounded.none}"
    padding: "0 14px"
    height: "{spacing.control-height}"
  button-secondary-hover:
    backgroundColor: "{colors.surface-raised}"
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
    textColor: "{colors.accent-deep}"
  focus-ring:
    outline: "2px solid {colors.accent}"
    outlineOffset: "2px"
  input:
    backgroundColor: "{colors.background}"
    textColor: "{colors.ink}"
    placeholderColor: "{colors.ink-muted}"
    borderColor: "{colors.line-strong}"
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
    borderColor: "{colors.line-strong}"
    rounded: "{rounded.none}"
    height: "32px"
  filter-chip-active:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.on-ink}"
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
    swapPause: "150ms"
    easing: "cubic-bezier(0.65, 0, 0.35, 1)"
---

# TRATO — Sistema de diseño

> Ámbito: `apps/web/**` y `packages/ui/**` (carril DEV-6). El bloque YAML de arriba es la **fuente de
> verdad de los valores** (la clave `shadcn` mapea los tokens a las variables de shadcn/ui, tal como se
> generaron y validaron en tweakcn); este texto explica cómo usarlos. Si este documento contradice a
> `PROMPT-IMPLEMENTACION.md` en comportamiento de producto, gana el spec. Los tokens se implementan como
> variables CSS en `@theme` (Tailwind v4) en D6-01 y los componentes en D6-02.

## 1. Carácter

TRATO es una herramienta donde alguien **firma compras con dinero real**. Tiene que parecer un
instrumento preciso, no una demo.

- **Vercel:** monocromo sobre casi negro, tipografía Geist, bordes finos, botón principal claro, cero adorno.
- **Render:** esquinas rectas (radio 0 en todo) y bordes de 1 px.
- **Sin color de acento:** `accent` es el mismo blanco roto que `ink`. Lo que destaca (foco, selección,
  enlaces, serie principal) lo hace por luminosidad, subrayado o borde, nunca por un tono propio. Así el
  único color de la interfaz es el de estado, y cuando aparece significa algo.
- **Revolut app:** cifras grandes y seguras (`numeral`), paneles amplios, la cantidad como protagonista.

Solo modo oscuro. No hay tema claro: un único tema evita mantener dos paletas y que una de las dos quede descuidada.

## 2. Lo que no hacemos

Patrones que hacen que una interfaz parezca generada y que este sistema excluye:

- Modo claro o un segundo tema. TRATO es solo oscuro.
- Negro puro (`#000`) de fondo o blanco puro para texto: cansan la vista y hacen vibrar el contraste.
- Brillos radiales detrás del hero, tarjetas con degradado, glassmorphism, sombras de color.
- Titulares que entran con desenfoque.
- Esquinas redondeadas en la interfaz: todo es recto (`rounded.none`). Lo único circular son los puntos
  del dithering.
- Una paleta paralela de grises o tonos casi iguales definidos elemento a elemento. Todo gris sale de
  `colors` del YAML.
- Texto de 9–12 px. El mínimo es `small` (13 px).
- Etiquetas en mayúsculas espaciadas encima de un titular («eyebrows»), en píldora o sin ella.
- Bloques de CSS que sobrescriben reglas anteriores en lugar de cambiarlas.
- Titulares a dos tonos (primera línea oscura, segunda gris).
- Iconos decorativos inventados (cubos apilados, destellos) y flechas en elementos que no son enlaces.
- Rejillas de tarjetas idénticas con icono + título + frase.
- Inventar cifras, clientes, logos, testimonios, premios o fotos. Si no hay dato real, no se muestra.

## 3. Reglas para quitar el aspecto «generado»

Aplican a todo componente y pantalla. Se revisan en cada PR (§12).

1. **Sin badges de relleno.** Nada de «Nuevo», «IA», «Beta», ni badges que repitan algo ya visible. Un
   badge solo existe si comunica un estado de dominio (§6).
2. **Sin etiquetas redundantes.** Un importe con divisa, una fecha o un nombre de vendedor no necesitan
   rótulo encima.
3. **Sin cursivas al azar.** Nunca se resalta una palabra suelta con cursiva o color.
4. **Mono solo donde hace falta.** `mono` es para IDs, hashes, claves públicas y código. Nunca para
   cifras, titulares ni etiquetas «técnicas».
5. **Sistema de diseño siempre.** Solo componentes de `@trato/ui` y tokens de este archivo.
6. **Mostrar el producto real.** Pantallas, capturas y stories con datos reales del contrato (fixtures),
   no textos de relleno.
7. **Agrandar lo principal.** Un elemento dominante por vista (el precio, la decisión, el KPI con
   `numeral`); todo lo demás baja de nivel.
8. **Agrupar con espacio, no con cajas.** Elementos relacionados a `inline-gap`/`control-gap`; grupos
   separados por `group-gap`; secciones por `section`. No añadir bordes o paneles para agrupar.
9. **Titulares concretos.** «3 ofertas esperan tu firma», no «Compras inteligentes, simplificadas».
10. **Destacar el CTA.** Un solo `button-primary` por zona; el resto `secondary` o `ghost`.
11. **Monocromo.** No hay color de acento: foco, selección, enlaces y serie principal usan `accent` (= `ink`).
    Los enlaces se distinguen por subrayado. Los colores de estado no son acentos: solo significan estado.
12. **Iconos coherentes.** Solo lucide, mismo trazo (1.75) y tamaño (16 px en texto, 20 px en
    navegación), y solo cuando aportan significado.
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
    datos.
20. **Animar feedback útil.** Solo animaciones que confirman algo: guardado, firmado, fila añadida,
    botón pulsado (§8).

## 4. Color

- Todo color se consume por token semántico (`bg-surface`, `text-ink-muted`, `border-line`…). Prohibidos
  hex literales, paleta cruda de Tailwind (`bg-red-100`) y valores arbitrarios en componentes.
- Jerarquía de superficie: en oscuro, **más elevado = más claro**. `background` (página e inputs) →
  `surface` (paneles) → `surface-raised` (cabeceras de tabla, hover, popovers, badge neutro). Las capas se
  separan con `line` y con ese paso de luminosidad, no con sombra.
- El botón principal es claro (`ink`) con texto `on-ink`; el destructivo usa `danger-solid` con texto
  `white`. `danger` (más claro) es solo para texto e iconos de error.
- Los fondos `*-subtle` son tintes muy oscuros: en badges el texto va en el color de estado, nunca en blanco.
- `line-strong` solo para el borde de controles interactivos (inputs, botón secundario).
- El color nunca es la única señal: todo estado lleva texto e icono.

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
  seleccionada `table-row-selected`, paginación «Cargar más» (cursor).
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

- Solo `opacity` y `transform`, con `motion.fast` (hover, pulsado), `motion.base` (cambios de estado) y
  `motion.overlay` (popover, diálogo), siempre con `motion.easing`.
- Animación permitida = feedback: confirmación de firma, guardado, fila nueva resaltada brevemente,
  cambio de banda tras recalcular.
- Prohibido: entradas de página, desenfoques, rebotes y parallax.
- Los bucles solo existen en el campo de puntos (§9), el indicador de carga (§9.2) y `ShiningText`.
- **`ShiningText`:** un brillo que recorre el texto en bucle (2 s, lineal), de `ink-muted` a `ink`. Solo
  para trabajo que un agente está haciendo **ahora**: «Redactando la contraoferta…», «Buscando ofertas…»,
  «Analizando el CSV…». Nunca en títulos, cifras o estados terminados. Lleva `role="status"`; con reduced
  motion queda estático en `ink-muted`.
- `prefers-reduced-motion`: se reduce todo a cambios de opacidad instantáneos.

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
- **Motivo (en prueba):** autómata celular elemental, regla 30, sembrado con una sola celda. La generación
  más nueva entra por arriba y el campo baja; las filas antiguas pierden intensidad hacia abajo. Es binario
  por naturaleza, así que no pasa por Atkinson: la escala de grises sale de la edad de la fila.
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
- Cada intercambio dura `swapDuration`, pausa `swapPause`; la secuencia de parejas (1–2, 2–3, 3–4, 2–3) se
  repite en bucle.
- Uso: modales de carga y esperas de más de 400 ms. Siempre con texto que diga qué se espera
  («Firmando decisión…») y `role="status"`. Con reduced motion: bolas quietas y el texto.

## 10. Accesibilidad e internacionalización

- WCAG 2.2 AA. Foco siempre visible con `focus-ring`; nunca `outline: none` sin sustituto.
- Objetivo táctil mínimo 24×24 px; 32 px en acciones de fila.
- `axe` en Storybook y Playwright; violaciones `serious`/`critical` bloquean el PR.
- Todo texto por `next-intl` (`es`, `en`, `zh`). Sin anchos fijos en botones o etiquetas: el español
  crece un 20–30 % respecto al inglés.
- Números, divisas y fechas con el locale activo vía `Intl`. Fechas relativas siempre con tooltip absoluto.

## 11. Código

- Tailwind v4 CSS-first: los tokens del YAML se declaran una vez en `@theme`
  (`apps/web/src/styles/globals.css`) y se reexportan en `packages/ui/src/styles.css` para Storybook.
- Variantes con `cva`, combinación con `cn()`. Sin `style={{}}` para color o espaciado, sin
  `!important`, sin CSS modules nuevos.
- Se cambia la regla existente; nunca se añade un bloque posterior que la sobrescriba.
- Cada componente de `packages/ui` llega con story (variantes, `es` y `zh`, datos reales) y test de axe.

### Prompt base para agentes que tocan UI

```text
Eres DEV-6. Construye <componente/vista> para TRATO siguiendo packages/ui/DESIGN.md al pie de la letra:
los valores del YAML son los únicos permitidos y las secciones 2 y 3 son obligatorias. Solo modo oscuro.
Usa componentes de @trato/ui, iconos lucide y textos vía next-intl (es/en/zh). La UI no calcula dinero ni
bandas: muestra lo que devuelve la API. Usa datos reales de los fixtures del contrato.
Implementa carga/vacío/error/datos. Entrega componente + story + test axe. Después renderiza, haz una
captura con Playwright, revísala contra la checklist de la sección 12 y corrige lo que falle antes de
terminar. Indica qué reglas comprobaste.
```

## 12. Checklist de PR

- [ ] Solo tokens de este archivo; ningún gris, color, radio o tamaño fuera del YAML.
- [ ] Nada de la sección 2 (tema claro, degradados, eyebrows, titulares a dos tonos, rejillas de tarjetas…).
- [ ] Sin badges de relleno ni etiquetas redundantes; mono solo en IDs/hashes.
- [ ] Un elemento dominante y un único CTA primario por zona; titular concreto y con `balance`.
- [ ] Radio 0 en todos los elementos de interfaz.
- [ ] Texto ≥ 13 px y contraste ≥ `ink-muted`.
- [ ] Cifras tabulares a la derecha; dinero solo con `MoneyDisplay`.
- [ ] Confianza y banda de precio junto al precio; firma junto al trato.
- [ ] Botones deshabilitados con razón visible.
- [ ] Carga, vacío, error y datos implementados; animaciones solo de feedback.
- [ ] Textos en `es`/`en`/`zh`, probado con textos largos; `axe` limpio; foco visible.
