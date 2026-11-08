# TRATO — Guía de estilos frontend

> Ámbito: `apps/web/**` y `packages/ui/**` (carril DEV-6). Esta guía define **cómo se ve y cómo se
> construye** la interfaz. Si contradice a `PROMPT-IMPLEMENTACION.md` en comportamiento de producto, gana
> el spec. La implementación de los tokens y componentes ocurre en D6-01 (Tailwind v4) y D6-02 (design
> system + Storybook); esta guía es la referencia contra la que se revisan esos PRs.

---

## 1. Principios

TRATO es una herramienta B2B donde un responsable humano **decide y firma compras con dinero real**.
El estilo tiene que transmitir precisión y confianza, no espectáculo.

1. **Claridad antes que decoración.** Cada píxel ayuda a decidir. Nada de gradientes, glassmorphism,
   ilustraciones genéricas ni sombras grandes. Referencias de tono: Linear, Stripe Dashboard, Vercel, Mercury.
2. **Densidad con jerarquía.** Pantallas de datos densas (tablas, comparativas), pero con una jerarquía
   tipográfica clara: un único elemento dominante por vista.
3. **El riesgo siempre visible.** La banda de confianza del vendedor va **siempre junto al precio**. El
   estado de firma va **siempre junto al trato**. Nunca se esconde un riesgo detrás de un clic.
4. **La UI muestra, no calcula.** Importes, bandas, puntuaciones y elegibilidad vienen de la API. La UI
   solo formatea (ver §7).
5. **Explicar lo bloqueado.** Un botón deshabilitado siempre dice por qué (criterio 16).
6. **Consistencia por tokens.** Ningún color, tamaño o radio se escribe a mano en un componente: todo sale
   de tokens (§2–§4).
7. **Accesible e internacional desde el día uno.** WCAG 2.2 AA y `es` / `en` / `zh` (§10, §11).

---

## 2. Color

### 2.1 Reglas

- Los colores se definen **una sola vez** como variables CSS en `globals.css` (bloque `@theme` de
  Tailwind v4) y se consumen con utilidades semánticas (`bg-primary`, `text-muted-foreground`,
  `bg-status-danger-subtle`…).
- **Prohibido** en componentes: hex/rgb/oklch literales, utilidades de paleta cruda (`bg-red-100`,
  `text-green-800`) y valores arbitrarios (`bg-[#123456]`). El `Badge` actual usa paleta cruda: se migra a
  tokens en D6-02.
- Formato: **OKLCH** (Tailwind v4 lo usa por defecto y da pasos de luminosidad perceptualmente uniformes).
- Cada color de superficie tiene su pareja `-foreground` con contraste ≥ 4.5:1 (texto) o ≥ 3:1 (iconos,
  bordes de controles).
- El color **nunca** es la única señal: toda banda/estado lleva además texto e icono.

### 2.2 Tokens base (propuesta)

Neutros fríos (slate) + un azul profundo como color de marca. Un solo acento; el resto del color se reserva
para **estado**, así el color significa algo cuando aparece.

| Token | Claro | Oscuro | Uso |
|---|---|---|---|
| `background` | `oklch(0.985 0.002 250)` | `oklch(0.16 0.01 255)` | Fondo de página |
| `surface` / `card` | `oklch(1 0 0)` | `oklch(0.20 0.012 255)` | Tarjetas, tablas, paneles |
| `surface-sunken` | `oklch(0.965 0.004 250)` | `oklch(0.13 0.01 255)` | Cabeceras de tabla, zonas inset |
| `foreground` | `oklch(0.21 0.02 260)` | `oklch(0.96 0.005 250)` | Texto principal |
| `muted-foreground` | `oklch(0.50 0.02 258)` | `oklch(0.70 0.015 255)` | Texto secundario, etiquetas |
| `border` | `oklch(0.92 0.006 255)` | `oklch(0.30 0.012 255)` | Bordes y divisores |
| `input` | `oklch(0.87 0.008 255)` | `oklch(0.34 0.012 255)` | Borde de controles |
| `primary` | `oklch(0.45 0.14 258)` | `oklch(0.70 0.13 255)` | Acción principal, enlaces, foco |
| `primary-foreground` | `oklch(0.99 0 0)` | `oklch(0.16 0.02 260)` | Texto sobre primary |
| `ring` | = `primary` | = `primary` | Anillo de foco |

### 2.3 Colores de estado

Cada estado tiene tres tokens: `status-<x>` (icono/borde fuerte), `status-<x>-subtle` (fondo de
badge/alerta) y `status-<x>-foreground` (texto sobre el subtle, contraste AA).

| Estado | Matiz OKLCH aprox. | Significado genérico |
|---|---|---|
| `success` | 150 (verde) | Correcto, dentro de presupuesto, firmado |
| `info` | 240 (azul) | Neutro informativo |
| `warning` | 80 (ámbar) | Requiere atención, no bloquea por sí solo |
| `danger` | 25 (rojo) | Bloqueo, descarte, firma inválida |
| `neutral` | — (gris) | Sin datos, pendiente, desconocido |

### 2.4 Mapeo de dominio → estado

Los componentes de dominio (§8) usan **solo** este mapeo. Nunca se inventan colores por pantalla.

| Concepto | Valor | Estado | Icono (lucide) |
|---|---|---|---|
| Confianza vendedor | `high` | success | `ShieldCheck` |
| | `medium` | info | `Shield` |
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
| Flags | `fx_provisional`, `financials_stale` | warning | `Info` / `History` |

> Nota: si el valor de la API no está en la tabla, se muestra como `neutral` con el texto crudo y se abre
> un issue. Nunca se colorea "a ojo".

---

## 3. Tipografía

- **Familia:** Inter (variable) vía `next/font` para latino; fallback `"Noto Sans SC", "PingFang SC",
  "Microsoft YaHei"` para `zh`. Monoespaciada: `JetBrains Mono` (o `ui-monospace`) solo para hashes,
  IDs y claves públicas.
- **Cifras:** todo número comparable (importes, puntuaciones, porcentajes, cuentas atrás) usa
  `tabular-nums` y se alinea a la derecha en tablas. Clase utilitaria `.num` = `font-variant-numeric:
  tabular-nums slashed-zero`.
- **Escala** (rem, base 16px). Pocos tamaños, usados siempre igual:

| Token | Tamaño / interlineado | Peso | Uso |
|---|---|---|---|
| `text-xs` | 12 / 16 | 500 | Badges, metadatos, cabeceras de tabla (mayúsculas no; tracking normal) |
| `text-sm` | 14 / 20 | 400 | **Texto por defecto de la app**, celdas, formularios |
| `text-base` | 16 / 24 | 400 | Texto largo (explicaciones, transcript) |
| `text-lg` | 18 / 28 | 600 | Título de tarjeta / panel |
| `text-xl` | 20 / 28 | 600 | Título de sección |
| `text-2xl` | 24 / 32 | 600 | Título de página |
| `text-3xl` | 30 / 36 | 600 | Cifra KPI (con `.num`) |

- Pesos permitidos: 400, 500, 600. Sin 700+ salvo KPIs excepcionales.
- Longitud de línea de texto corrido: máx. ~72 caracteres (`max-w-prose`).
- `zh`: interlineado +10 % (`leading-relaxed`) y sin `italic`.

---

## 4. Espaciado, layout, forma y elevación

- **Espaciado:** escala de 4 px de Tailwind. Valores habituales: `1` (4), `2` (8), `3` (12), `4` (16),
  `6` (24), `8` (32). Evitar `5`, `7` y valores arbitrarios.
  - Dentro de un control: 8–12. Entre controles relacionados: 8–16. Entre secciones: 24–32.
- **Densidad:** dos modos para tablas: `comfortable` (fila 44 px) por defecto y `compact` (fila 32 px)
  para comparativas. Se elige con un prop, no con clases sueltas.
- **Layout de app:** barra lateral 240 px (colapsable a 64 px), cabecera 56 px con el **indicador de
  sesión de firma** fijo a la derecha, contenido con `max-w-screen-2xl` y padding `px-6`.
- **Rejilla:** 12 columnas en ≥ `lg`; en móvil una columna. El dashboard es *desktop-first* (uso
  profesional) pero ninguna vista puede romperse a 360 px de ancho.
- **Radios:** `--radius: 0.5rem`. `rounded-sm` (4) para badges/inputs pequeños, `rounded-md` (6) controles,
  `rounded-lg` (8) tarjetas y diálogos. Nada más redondo; nada de píldoras salvo chips de filtro.
- **Elevación:** se separa por **borde + fondo**, no por sombra. Sombras solo en capas flotantes:
  `shadow-sm` popovers/menús, `shadow-lg` diálogos. Las tarjetas llevan `border` y sin sombra.
- **Bordes:** 1 px `border-border`. Divisores de tabla horizontales únicamente.

---

## 5. Iconografía e imágenes

- Solo **lucide-react**, trazo 1.5–2 px, tamaño 16 px en texto `sm`, 20 px en botones `lg`/navegación.
- Icono + texto siempre; icono solo únicamente en botones de toolbar con `aria-label` y tooltip.
- Sin ilustraciones decorativas ni emojis en la UI. Los estados vacíos usan un icono, un título y una acción.

---

## 6. Movimiento

- Duraciones: 120 ms (hover, color), 200 ms (popover, tooltip), 250 ms (diálogo/drawer). Curva
  `cubic-bezier(0.2, 0, 0, 1)`.
- Animar solo `opacity` y `transform`. Nada de rebotes, parallax ni animaciones de entrada de página.
- Respetar `prefers-reduced-motion`: se desactiva todo salvo cambios de opacidad.
- La cuenta atrás de la sesión de firma no parpadea; en los últimos 60 s cambia a `warning` y anuncia una
  vez por `aria-live="polite"`.

---

## 7. Dinero, números, fechas

- **Formato solo con `Intl`**, nunca concatenando strings. Componente `MoneyDisplay` recibe
  `{amount_minor, currency}` de la API y formatea con `Intl.NumberFormat(locale, {style: 'currency',
  currency})`. No suma, no convierte, no redondea por su cuenta.
- Mostrar siempre el código o símbolo de divisa. Cuando un importe se convirtió, mostrar el original en
  tooltip (`fx_rate`, `fx_as_of`, `fx_source`) y el badge `fx_provisional` si aplica.
- Negativos con signo menos real (`−`) y color `danger` solo si significan pérdida/excedido, no por ser
  negativos.
- Porcentajes y puntuaciones con los decimales que devuelve la API; no se redondea en cliente.
- Fechas: `Intl.DateTimeFormat`; relativas ("hace 3 h") solo con tooltip de fecha absoluta y zona horaria.

---

## 8. Componentes

### 8.1 Base (`packages/ui`)

shadcn/ui sobre Radix, con `class-variance-authority` para variantes y `cn()` para combinar clases.
Lista objetivo D6-02: Button, Input, Label, Select, Checkbox, Switch, Textarea, Card, Badge, Table
(TanStack), Dialog, Sheet, Tabs, Tooltip, Popover, DropdownMenu, Toast, Skeleton, Progress, Alert.

**Botones**

| Variante | Uso | Máx. por vista |
|---|---|---|
| `default` (primary) | La acción principal (p. ej. "Firmar y seguir") | 1 por zona |
| `secondary` / `outline` | Acciones alternativas | — |
| `ghost` | Toolbars, acciones de fila | — |
| `destructive` | Descartar, revocar clave. Siempre con confirmación | 1 |
| `link` | Navegación inline | — |

- Etiquetas con verbo + objeto ("Descartar oferta", no "OK").
- Acciones que firman llevan icono `PenLine` y el texto "Firmar…" para que el usuario sepa que firma.
- Deshabilitado = `disabled` + `DisabledReason` (tooltip accesible con la razón de la API).

### 8.2 Dominio (`packages/ui`, D6-02)

| Componente | Contrato visual |
|---|---|
| `ConfidenceBandBadge` | Badge subtle + icono + texto de banda + score `.num`. Popover con desglose de señales y `model_version`. |
| `PriceBandBadge` | Igual; popover con mediana de referencia, z-score y tamaño de muestra. |
| `FinancialVerdictBadge` | Igual; popover con razones numéricas. |
| `SignatureStatusBadge` | `signed` / `pending` / `invalid`; popover con firmante, hora y hash (mono, truncado con copiar). |
| `MoneyDisplay` | Solo formato (§7). Variante `size="kpi"`. |
| `DisabledReason` | Envoltorio que muestra tooltip con la razón y la expone por `aria-describedby`. |
| `SigningSessionIndicator` | Cabecera: firmante, `mm:ss`, firmas restantes; estado expirado = solo lectura + botón "Reautenticar para firmar". |

**Regla de la fila de oferta:** `precio · PriceBand · ConfidenceBand · Veredicto · Firma`, siempre en ese
orden y siempre visibles en la tabla; nunca solo en el detalle.

### 8.3 Tablas

- Cabecera `surface-sunken`, `text-xs` `muted-foreground`, sticky.
- Números alineados a la derecha con `.num`; texto a la izquierda; badges centrados no.
- Hover de fila sutil (`bg-muted/50`), fila seleccionada con borde izquierdo `primary`.
- Ordenación y filtros visibles; paginación por cursor ("Cargar más"), no números de página.

### 8.4 Formularios

- Label encima, ayuda debajo en `muted-foreground`, error debajo en `danger` con icono, vinculado por
  `aria-describedby`. Validación al salir del campo y al enviar, no al teclear.
- Campos de dinero: input de texto decimal con divisa explícita; nunca `type="number"`.
- Credenciales: nunca se guardan en estado cliente; el campo se vacía tras enviar.

### 8.5 Estados de pantalla

Toda vista que carga datos implementa los cuatro: **cargando** (Skeleton con la forma final, no spinners
de página), **vacío** (icono + título + acción), **error** (Alert `danger` con el `title`/`detail` de
problem+json y "Reintentar") y **datos**. `428 reauth_required` nunca es un error visible: abre el flujo
de passkey (D6-03).

### 8.6 Gráficas

Recharts con los tokens: series categóricas en neutros + `primary`; bandas de sanity como áreas
`warning-subtle`/`danger-subtle`; ejes `muted-foreground` `text-xs`; sin 3D, sin gradientes; tooltips con
`MoneyDisplay`. Siempre una tabla o texto alternativo para lectores de pantalla.

---

## 9. Contenido y tono

- Español de España por defecto, tuteo profesional, frases cortas. Sin jerga interna (`atypical`) en la
  UI: se traduce ("Precio atípico").
- Mensajes de bloqueo: **qué** pasa + **por qué** + **qué hacer** ("No se puede comprar: la situación
  financiera tiene más de 30 días. Reimporta el CSV.").
- Sin signos de exclamación ni emojis. Mayúscula solo inicial ("Cola de gate", no "Cola De Gate").

---

## 10. Accesibilidad (WCAG 2.2 AA, obligatorio)

- Contraste AA verificado para cada pareja de tokens en claro y oscuro (test automático en D6-02).
- Foco visible siempre: `focus-visible:ring-2 ring-ring ring-offset-2 ring-offset-background`. Nunca
  `outline-none` sin sustituto.
- Objetivo táctil mínimo 24×24 px (2.5.8); 32 px en acciones de fila.
- Todo componente Radix conserva su semántica; no se reemplazan `button` por `div`.
- `axe` en Storybook y en Playwright; un PR con violaciones `serious`/`critical` no se mergea.

---

## 11. Internacionalización

- Ningún texto literal en componentes: todo por `next-intl` (`es`, `en`, `zh`).
- Diseñar para +35 % de longitud (el alemán no está, pero `en`→`es` crece ~20–30 %): nada de anchos fijos
  en botones ni etiquetas truncadas sin tooltip.
- Números, divisas y fechas con el locale activo (§7).

---

## 12. Modo oscuro

Soportado vía clase `.dark` y tokens; cada token de §2 tiene valor oscuro. En oscuro se baja la saturación
de los `status-*-subtle` y se usan superficies más claras para elevar (no sombras). Se prueba cada
componente en Storybook en ambos temas.

---

## 13. Convenciones de código de estilos

- Tailwind v4, configuración **CSS-first** con `@theme` en `apps/web/src/styles/globals.css`; los tokens
  viven también exportados desde `packages/ui/src/styles.css` para Storybook.
- Variantes con `cva`; nunca condicionales de clases a mano en JSX largos. `cn()` para permitir
  `className` de override.
- Prohibido: `style={{}}` para colores/espaciado, valores arbitrarios `[...]` (salvo `grid-template`
  justificado), `!important`, CSS modules nuevos.
- Orden de clases automático con `prettier-plugin-tailwindcss` (D1-01).
- Cada componente nuevo de `packages/ui` llega con story (todas las variantes, ambos temas, `es`/`zh`) y
  test de accesibilidad.

---

## 14. Cómo usar IA para diseñar y construir la UI

La IA genera UI "profesional" cuando **se le restringe**, no cuando se le da libertad. Sin contexto,
cualquier modelo produce el mismo look genérico (gradiente morado, tarjetas con sombra, emojis). El flujo:

1. **Contexto fijo.** Pasar siempre esta guía + `globals.css` + la lista de componentes de `packages/ui`.
   Pedir explícitamente: "usa solo componentes de `@trato/ui` y tokens semánticos; nada de colores
   literales".
2. **Referencia visual concreta.** Adjuntar capturas de una pantalla de referencia (propia o de producto
   con el tono buscado) o el frame de Figma, y describir la jerarquía: qué es lo más importante en la vista.
3. **Datos realistas.** Dar fixtures reales del contrato (importes grandes, nombres largos en chino,
   valores `insufficient_data`). Los diseños con datos de juguete se rompen con datos reales.
4. **Generar → ver → criticar → iterar.** Renderizar (Storybook o `next dev`), hacer captura con
   Playwright y pedir a la IA que critique su propia captura contra esta guía (contraste, alineación de
   números, jerarquía, estados vacíos/error) antes de dar por buena la vista.
5. **Componentes, no pantallas enteras.** Pedir primero el componente (`ConfidenceBandBadge` con sus
   stories), luego la composición. Una pantalla grande de una vez acumula inconsistencias.
6. **Verificación automática.** Lint, `axe`, regresión visual de Storybook. La IA no revisa su propio
   trabajo como único control.

**Prompt base** para cualquier agente que toque UI:

```
Eres DEV-6. Construye <componente/vista> para TRATO.
Restricciones: sigue packages/ui/STYLEGUIDE.md al pie de la letra. Usa solo componentes de @trato/ui,
tokens semánticos de globals.css, iconos lucide y textos vía next-intl (es/en/zh). Prohibidos colores
literales, valores arbitrarios de Tailwind, sombras en tarjetas, gradientes y emojis. La UI no calcula
dinero ni bandas: solo muestra lo que devuelve la API. Implementa estados loading/empty/error/data.
Entrega: componente + story (claro/oscuro, es/zh) + test axe. Después, haz una captura con Playwright,
compárala con la guía y corrige lo que no cumpla antes de terminar.
```

---

## 15. Checklist de revisión de PR (UI)

- [ ] Solo tokens semánticos; sin colores literales ni valores arbitrarios.
- [ ] Bandas de confianza y precio junto al precio; estado de firma junto al trato.
- [ ] Botones deshabilitados con razón visible y accesible.
- [ ] Cuatro estados (loading/empty/error/data) implementados.
- [ ] Números con `.num` y alineados a la derecha; dinero solo con `MoneyDisplay`.
- [ ] Textos traducidos en `es`/`en`/`zh`; probado con textos largos.
- [ ] `axe` sin violaciones serias; foco visible; teclado completo.
- [ ] Story en claro y oscuro.
