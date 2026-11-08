---
name: TRATO navegación
description: Mapa de pantallas, rutas, guardas, modales y flujos de la app web de TRATO. Complementa a packages/ui/DESIGN.md (cómo se ve) con cómo se llega a cada sitio.
locales: [es, en, zh]
routePrefix: "/[locale]"
landing:
  authenticated: /decisiones
  onboardingIncomplete: /onboarding/empresa
  anonymous: /acceso
primaryNav:
  - { label: Decisiones, href: /decisiones, badge: "pendientes en la cola de gate" }
  - { label: Misiones, href: /misiones }
  - { label: Aprobaciones, href: /aprobaciones, badge: "firmas que te esperan" }
  - { label: Empresa, href: /empresa/reglas }
companyNav:
  - { label: Reglas de decisión, href: /empresa/reglas }
  - { label: Datos financieros, href: /empresa/finanzas }
  - { label: Cuentas de plataformas, href: /empresa/cuentas }
  - { label: Firma y claves, href: /empresa/firma }
  - { label: Auditoría, href: /empresa/auditoria, roles: [admin, owner] }
modalDepthMax: 1
toastDuration: 6s
---

# Navegación de TRATO

Este documento fija **qué pantallas existen, cómo se llega a cada una, qué overlays hay y cuándo se usan**. El aspecto
(colores, tipografía, componentes) está en `packages/ui/DESIGN.md`. Los wireframes están en el lienzo "TRATO wireframes";
cada pantalla de la tabla 2 indica su artboard.

Reglas de producto que condicionan la navegación (de `PROMPT-IMPLEMENTACION.md`):

- El onboarding es **bloqueante**: sin snapshot financiero `active` no se lanza ninguna misión (§3.1).
- Toda decisión es una **acción firmada** dentro de una sesión de firma de 15 minutos, fija y no deslizante (§5.10.4).
- El dashboard es una **cola de trabajo**, no un informe (§3.8): la pantalla de inicio es Decisiones.
- Un `428 reauth_required` nunca hace perder el contexto: se reautentica y se reintenta en el sitio (§5.2).

## 1. Principios

1. **La URL es el estado compartible.** Todo lo que un responsable quiera enviar a otro (una oferta, un filtro, una
   pestaña, el perfil de ranking) vive en la ruta o en la query. Los paneles abiertos, borradores y foco viven en
   Zustand y no se comparten.
2. **Un nivel de overlay como máximo.** Nunca un diálogo encima de otro. La única excepción es la hoja nativa de passkey
   del sistema operativo, que no controlamos.
3. **Decidir no cambia de pantalla.** Firmar, aparcar, descartar o renegociar se confirma en un panel dentro del detalle
   del trato (lateral en escritorio, hoja inferior en móvil). Al firmar, el trato se marca como firmado y el foco pasa al
   siguiente de la cola.
4. **Atrás siempre funciona.** Los diálogos no añaden entradas al historial. Cambiar de trato, de pestaña o de filtro sí
   (con `replace` para filtros, `push` para trato y pestaña).
5. **Nada se esconde para bloquear.** Una acción no disponible se muestra deshabilitada con el motivo de la API en texto
   visible y en tooltip (criterio 16). Un enlace a una pantalla sin permiso tampoco se esconde: lleva a la pantalla con
   el estado "sin permiso".
6. **Sin callejones.** Cada estado vacío o de error ofrece el siguiente paso con un enlace real (ver 7).

## 2. Mapa de rutas

Todas bajo `/[locale]` (`es`, `en`, `zh`). Rol mínimo: `viewer` puede ver todo lo que no diga otra cosa, pero no firma.

| Ruta | Pantalla | Artboard | Rol | Guarda |
|---|---|---|---|---|
| `/acceso` | Acceso (correo, passkey, SSO) | `Login*.dc.html` | anónimo | autenticado → `landing` |
| `/onboarding/[paso]` | Alta de empresa, 7 pasos: `empresa`, `sector`, `cuentas`, `presupuesto`, `politica`, `negociacion`, `finanzas` | `OnbAlta` | owner, admin, finance | onboarding completo → `/decisiones` |
| `/onboarding/finanzas/[importId]` | Revisión del CSV (mapeo, filas rechazadas, avisos) | `OnbCSV` | owner, admin, finance | import inexistente → `/onboarding/finanzas` |
| `/onboarding/finanzas/[importId]/activar` | Capacidad, envelopes, umbrales y activación firmada | `OnbResumen` | owner, admin, finance | import con filas sin mapear → paso anterior |
| `/decisiones` | Cola de gate y tratos, con detalle a la derecha | `Estilo` | todos | onboarding |
| `/decisiones/[dealId]` | Igual, con el trato seleccionado (enlace directo) | `Estilo` | todos | onboarding |
| `/decisiones/[dealId]/transcripcion` | Transcripción completa en el panel izquierdo | `Estilo` | todos | onboarding |
| `/decisiones/gate` | Cola de gate en tabla, agrupada | `Gate` | todos | onboarding |
| `/misiones` | Lista de misiones | pendiente de diseñar | todos | onboarding |
| `/misiones/nueva` | Petición en lenguaje natural y revisión | `Peticion` | buyer, finance, admin, owner | snapshot `active`; si no, banner con enlace a importar |
| `/misiones/[missionId]` | Misión en curso: fases, ofertas, actividad SSE | `Mision` | todos | — |
| `/misiones/[missionId]/negociaciones/[negId]` | Transcripción en vivo, aprobación de borradores, takeover | `Negociacion` | buyer, finance, admin, owner para actuar | — |
| `/misiones/[missionId]/comparativa` | Finalistas, distribución de precios, ahorro | `Comparativa` | todos | misión en valoración o cerrada |
| `/aprobaciones` | Bandeja: por firmar, en curso, cerradas | `Aprobaciones` | todos | onboarding |
| `/aprobaciones/[approvalId]` | Doble control, documentos, seguimiento | `Aprobaciones` | todos | — |
| `/empresa/reglas` | Reglas de decisión versionadas | `Config` | ver: todos; cambiar: finance, admin, owner | — |
| `/empresa/finanzas` | Snapshot activo, histórico, reimportar | pendiente (reusa `OnbCSV` y `OnbResumen`) | owner, admin, finance | — |
| `/empresa/cuentas` | Cuentas de plataformas | reusa el paso `cuentas` de `OnbAlta` | owner, admin | — |
| `/empresa/firma` | Tus claves, alta y revocación | `Firma` | buyer, finance, admin, owner | — |
| `/empresa/auditoria` | Cadena de hashes, eventos, verificar decisión | `Auditoria` | admin, owner | otro rol → estado "sin permiso" |
| `/403`, `/404`, `/error` | Errores de página | `EstadosUI` | — | — |

**Pendientes de diseñar:** lista de misiones, Empresa · Datos financieros (histórico de snapshots), menú de usuario
(perfil, idioma, cerrar sesión) y la versión móvil de la cabecera.

## 3. Guardas y redirecciones

Se evalúan en este orden en el middleware (DEV-1 es dueño de `src/middleware.ts`; aquí se define el comportamiento que
la UI espera):

1. **Sin sesión** → `/acceso?next=<ruta>`. Tras entrar, se vuelve a `next` si es una ruta interna.
2. **Onboarding incompleto** (sin snapshot `active`) → `/onboarding/<primer paso pendiente>`. Excepciones: `/empresa/*`
   y `/onboarding/*`.
3. **Rol insuficiente** → la pantalla se carga con el estado "sin permiso"; no se redirige.
4. **Recurso de otro tenant o inexistente** → `/404`. Nunca se distingue entre ambos.
5. **`financials_stale`** no redirige: badge en la cabecera, banner en Decisiones y `follow` deshabilitado con motivo.
   El badge y el banner enlazan a `/empresa/finanzas`.

## 4. Navegación global

**Cabecera** (todas las pantallas autenticadas salvo el onboarding):

- Izquierda: `TRATO` (enlace a `/decisiones`), navegación primaria del YAML, badge `financials_stale` si aplica.
- Derecha: **indicador de sesión de firma**, siempre visible. Estados: sin sesión (botón "Abrir sesión de firma"),
  activa (`mm:ss` + firmas restantes), caduca pronto (< 2 min, badge naranja), caducada o sin firmas (badge rojo y botón
  "Reautenticar para firmar"). Pulsarlo abre el diálogo **Abrir sesión de firma**.
- Después, menú de usuario: idioma, tema del sistema, cerrar sesión.
- La pestaña activa se marca con subrayado de 2 px en `ink`; los contadores de badge usan cifras tabulares.

**Onboarding:** cabecera reducida (`TRATO` + "Configurar empresa · paso N de 7" + estado de guardado). Lista de pasos a la
izquierda, navegable en cualquier orden. Panel del asistente a la derecha (en móvil, pestaña "Asistente").

**Empresa:** subnavegación horizontal bajo la cabecera con `companyNav`.

**Móvil (< 768 px):** la navegación primaria pasa a una barra inferior de 4 destinos; el indicador de firma queda arriba
en formato compacto (`mm:ss`). Los layouts lista + detalle muestran solo la lista y el detalle entra como pantalla nueva
(`push`).

## 5. Flujos principales

### 5.1 Primer acceso de una empresa
`/acceso` → `/onboarding/empresa` → … → `/onboarding/finanzas` (subir CSV) → `/onboarding/finanzas/[id]` (revisar)
→ `/onboarding/finanzas/[id]/activar` → **diálogo de passkey** (reautenticación inmediata) → `/misiones/nueva`
con el toast "Snapshot de octubre activo".

### 5.2 Lanzar y seguir una misión
`/misiones/nueva` → "Lanzar misión" → `/misiones/[id]`. Desde la tabla de ofertas:
- fila en negociación o con mensaje por aprobar → `/misiones/[id]/negociaciones/[negId]`;
- fila en gate → `/decisiones/[dealId]`;
- al terminar la valoración, el botón "Ver comparativa" lleva a `/misiones/[id]/comparativa`, y desde ahí cada finalista
  a `/decisiones/[dealId]`.

### 5.3 Decidir un trato
`/decisiones` → elegir fila → `/decisiones/[dealId]` → botón de acción → **panel de confirmación** (lo que se va a
firmar, campos obligatorios de la acción) → "Firmar decisión". Si hace falta passkey (sesión caducada, sin firmas,
importe alto, `override_discard`), el panel muestra el aviso y el botón pasa a "Autenticar con passkey y firmar". Al
terminar: toast con el hash y foco en la siguiente fila.

### 5.4 Negociación semiautomática y takeover
`/misiones/[id]/negociaciones/[negId]`: cada borrador espera "Aprobar y enviar". "Tomar el control" es inmediato y
reversible (sin diálogo); "Abortar" pide confirmación. Un escalado (pago fuera de plataforma, datos sensibles) crea un
elemento en la cola de gate y un aviso en la negociación con enlace a `/decisiones/[dealId]`.

### 5.5 Doble control
Primera firma en `/decisiones/[dealId]` → el trato pasa a `/aprobaciones` como "Falta segunda firma". El primer
firmante ve "Añadir segunda firma" deshabilitado con motivo y el botón "Pedir firma a Finanzas". El segundo firmante
entra por la notificación o por la bandeja.

### 5.6 Cambiar una regla
`/empresa/reglas` → "Cambiar" en una fila → panel lateral "Cambio propuesto" con diff, impacto calculado por el servidor
y motivo obligatorio → "Firmar con passkey" → nueva versión en el historial.

## 6. Overlays

Tipos (Radix vía `@trato/ui`):

- **Dialog**: tarea corta que bloquea, con foco atrapado. Esc y clic fuera cierran salvo que se indique.
- **AlertDialog**: confirmación de algo irreversible; sin cierre por clic fuera.
- **Panel**: inline dentro de la pantalla (no es modal); en móvil se presenta como hoja inferior.
- **Popover / Tooltip**: información sin acción principal.
- **Toast**: confirmación de algo ya hecho; nunca un error que exija actuar.

| Overlay | Tipo | Se abre desde | Contenido | Cierre |
|---|---|---|---|---|
| Abrir sesión de firma | Dialog | indicador de firma; primera acción firmada sin sesión | indicador de carga de 4 bolas, "Confirma con tu passkey", duración y firmas máximas | Cancelar, Esc. Bloqueado mientras el navegador espera a la passkey |
| Reautenticación por 428 | Dialog | cualquier llamada que devuelva `428 reauth_required` | motivo legible (cambio de red, dispositivo, clave revocada…), resumen de la decisión pendiente | tras passkey reintenta la misma llamada; Cancelar deja la decisión preparada |
| Reautenticación inmediata | Panel (dentro del de confirmación) | importe > `signing.high_value_reauth_above`, `override_discard`, activar snapshot, cambiar reglas, operar claves | aviso naranja + "Autenticar con passkey y firmar" | Cancelar |
| Confirmar decisión | Panel | botones de acción del trato y de la cola de gate | payload que se firma; `discard`: código + comentario; `hold`: fecha; `renegotiate`: instrucciones y rondas restantes; `override_discard`: motivo; `fx_provisional`: casilla de aceptación | Cancelar, o cambiar de trato (se conserva el borrador) |
| Alta de clave | Dialog | primera firma de un usuario sin clave; `/empresa/firma` | explicación de la clave no exportable, huella, "Crear y registrar" | Ahora no |
| Navegador sin Ed25519 | Banner inline | cualquier pantalla con acciones firmadas | motivo y navegadores compatibles | no se cierra; las acciones quedan deshabilitadas con motivo |
| Revocar clave | AlertDialog + passkey | `/empresa/firma` | consecuencias: la sesión se cierra, las firmas antiguas siguen verificando | Cancelar |
| Abortar negociación | AlertDialog | negociación | "La transcripción queda guardada; el vendedor no recibe aviso" | Cancelar |
| Cancelar misión | AlertDialog | misión | qué negociaciones se detienen | Cancelar |
| Descartar cambio de regla | AlertDialog | salir de `/empresa/reglas` con un cambio sin firmar | — | Seguir editando |
| Volver a entrar en una plataforma | Dialog | cuenta con sesión caducada (onboarding, cuentas, petición) | pasos guiados; las credenciales van directas al almacén cifrado | Cancelar |
| Desglose de confianza | Popover | `ConfidenceBandBadge` | señales por grupo con su valor | Esc, clic fuera |
| Motivo de acción deshabilitada | Tooltip + texto visible | botones deshabilitados | motivo de la API | — |
| Firma hecha, mensaje enviado, credenciales guardadas, conexión en vivo recuperada | Toast | tras la confirmación del servidor, nunca antes | texto + enlace (hash, transcripción) | 6 s o cerrar |

Reglas de overlays:

- **Nunca** se muestra un éxito antes de que la API lo confirme. Mientras tanto, el botón muestra el texto en
  `ShiningText` ("Firmando…", "Enviando…") y, si tarda más de 1 s, el indicador de 4 bolas.
- Si la sesión de firma caduca con un panel de confirmación abierto, el panel **se queda** con lo escrito y cambia el
  botón a reautenticar. Nada se pierde.
- El foco vuelve al elemento que abrió el overlay al cerrarlo. Los diálogos llevan título (`aria-labelledby`) y el
  primer foco va a la acción menos destructiva.
- Los overlays no cambian la URL, salvo la transcripción del trato, que es enlazable.

## 7. Estados vacíos y de error (salidas)

| Estado | Dónde | Salida |
|---|---|---|
| Cola vacía | `/decisiones` | "Ver misiones en curso" → `/misiones` |
| Misión sin ofertas válidas | `/misiones/[id]` | "Ver las descartadas" (filtro) · "Ampliar plataformas" → `/misiones/nueva` con la petición precargada |
| Conexión en vivo perdida | misión, negociación | reintento automático; badge "Sin conexión en vivo" hasta recuperar |
| Error del servidor | cualquier pantalla | "Reintentar" + traza; nunca se da por hecho nada |
| Sin permiso | cualquier pantalla | texto con el rol necesario; acciones deshabilitadas |
| Datos financieros caducados | cabecera, Decisiones | "Reimportar CSV" → `/empresa/finanzas` |
| Sin snapshot activo | `/misiones/nueva` | "Importar CSV financiero" → `/onboarding/finanzas` |

## 8. Teclado

- `j` / `k`: siguiente / anterior en la cola y en las tablas con selección. `Enter` abre el detalle.
- `Esc`: cierra el overlay abierto; si no hay, vuelve de la transcripción al detalle.
- No hay atajos para firmar ni para acciones destructivas.
- Los atajos solo se activan con el foco fuera de campos de texto y se listan en el menú de usuario.

## 9. Cómo verlo en el lienzo

En el lienzo "TRATO wireframes", pulsa ▶ en cualquier artboard marcado como interactivo. La navegación primaria, los
pasos del onboarding y los botones que cambian de pantalla son enlaces reales entre artboards. Los overlays de la
sección 6 se ven en `Estilo` (panel de confirmación y reautenticación), `Firma` y `Negociacion`.

Las piezas comunes son componentes del lienzo que importan todas las pantallas; cambiar uno cambia todas:
`UiCabecera` (navegación primaria de la sección 4), `UiChipFirma`, `UiEmpresaNav` (`companyNav`), `UiOnbCabecera`,
`UiBoton`, `UiBadge`, `UiCargando` y `UiMaqueta`. Los destinos de la navegación viven en `UiCabecera` y `UiEmpresaNav`,
así que una ruta nueva se añade allí y en la tabla 2 de este documento.
