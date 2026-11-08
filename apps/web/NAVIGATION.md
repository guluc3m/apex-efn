# Navegación de APEX

Este documento describe cómo se navega entre pantallas: qué enlaza con qué, qué cabecera y subnavegación
aparece en cada pantalla y qué pantallas no tienen entrada desde la app. Es la referencia para
implementar las rutas de `apps/web` y para revisar el lienzo de diseño.

**Fuente de verdad visual:** el lienzo Design «APEX · wireframes» (https://claude.ai/artifact/3cfVz483eqwBBfvTSpnizf),
archivos `project/*.dc.html`. Los componentes compartidos son `UiCabecera` (navegación primaria),
`UiEmpresaNav` (subnavegación de Empresa) y `UiOnbCabecera` (solo lo usa el resumen del onboarding; ver §7).

> **Regla:** cualquier cambio en el lienzo o en el código que altere una ruta, un enlace, la cabecera, la
> subnavegación o el destino de un botón obliga a actualizar este documento en el mismo cambio y a
> informarlo en la descripción del cambio. Ver `AGENTS.md`, sección «Navegación».

---

## 1. Principios

- Una pantalla de producto usa **una** cabecera compartida (`UiCabecera`). Si es de Empresa, añade
  `UiEmpresaNav`. No hay cabeceras escritas a mano.
- Todo botón con destino lleva a una pantalla de este documento. Un botón sin destino se marca como
  pendiente en §8, no se deja con un enlace inventado.
- Las pantallas de exploración (estados, sistema visual, plan, variantes de login) no forman parte de la
  navegación de producto; están listadas en §8.
- La cabecera siempre tiene el selector de idioma (`UiIdioma`) en el extremo derecho, después del
  indicador de firma.

## 2. Mapa de pantallas de producto

| Archivo | Pantalla | Cabecera (`activa`) | Entra desde | Sale a |
|---|---|---|---|---|
| `Estilo.dc.html` | Tratos (Decisiones) | Decisiones | Cabecera «Decisiones», pestaña «Tratos» de Cola, «Decidir sobre Vendedor A» (Comparativa) | `OnbCSV` (aviso de datos caducados), `Gate` (pestaña «Cola de gate») |
| `Gate.dc.html` | Cola de gate | Decisiones | Pestaña «Cola de gate» de Tratos, «Negociación» | `Estilo` (pestaña «Tratos») |
| `Main.dc.html` | Cola y tratos (versión de referencia) | Decisiones | Sin entrada desde la app (ver §8) | Cabecera: `Estilo`, `Mision`, `Config` |
| `Mision.dc.html` | Misión en curso | Misiones | Cabecera «Misiones», «Lanzar misión» (Peticion) | `Peticion` («Nueva misión»), `Comparativa`, `Negociacion`, `Estilo` |
| `Peticion.dc.html` | Nueva misión (lenguaje natural → petición estructurada) | Misiones | «Nueva misión» en Misiones | `Mision` («Volver a la misión», «Lanzar misión») |
| `Comparativa.dc.html` | Comparativa de finalistas | Decisiones | «Ver comparativa» en Misión | `Estilo` («Decidir sobre Vendedor A») |
| `Negociacion.dc.html` | Negociación en vivo | Misiones | «Abrir negociación» en Misión | `Mision` («Volver a la misión»), `Gate` |
| `Aprobaciones.dc.html` | Aprobaciones y doble control | Aprobaciones | Cabecera «Aprobaciones» | — |
| `Config.dc.html` | Reglas de decisión (Empresa) | Empresa | Cabecera «Empresa», subnavegación «Reglas de decisión» | — |
| `OnbAlta.dc.html` | Alta de empresa, pasos 1–6 | Empresa | Subnavegación «Cuentas de plataformas» | `OnbCSV` |
| `OnbCSV.dc.html` | Datos financieros (revisión del CSV) | Empresa | Subnavegación «Datos financieros», aviso «Datos financieros caducados», «Reimportar CSV» | `OnbAlta` («Corregir y volver a subir»), `OnbResumen` |
| `OnbResumen.dc.html` | Resumen financiero y activación | Empresa | `OnbCSV` («Revisar resultado y activar») | `OnbCSV` («Volver a revisar el CSV»), `Mision` («Activar con passkey») |
| `Firma.dc.html` | Firma de decisiones | Empresa | Subnavegación «Firma y claves» | — |
| `Auditoria.dc.html` | Registro de auditoría | Empresa | Subnavegación «Auditoría» | — |
| `Login.dc.html` | Acceso | — (sin cabecera) | «Salir» en la cabecera | `Estilo`, `OnbAlta` |

Nota sobre el alta: `OnbAlta` y `OnbCSV` usan `UiCabecera` + `UiEmpresaNav` (subnavegación de Empresa con el
paso del alta dentro de «Cuentas de plataformas» / «Datos financieros»). El flujo completo de alta va
`OnbAlta → OnbCSV → OnbResumen → Mision`.

## 3. Navegación primaria (`UiCabecera`)

Aparece en todas las pantallas de producto excepto el resumen del onboarding y el acceso.

| Elemento | Destino | Estado activo |
|---|---|---|
| Logo | — (decorativo en el lienzo; en la app, al inicio) | — |
| Decisiones | `Estilo.dc.html` | `Decisiones` |
| Misiones | `Mision.dc.html` | `Misiones` |
| Aprobaciones | `Aprobaciones.dc.html` | `Aprobaciones` |
| Empresa | `Config.dc.html` | `Empresa` |
| Aviso «Datos financieros caducados» (solo si `caducados`) | `OnbCSV.dc.html` | — |
| Indicador de firma (`UiChipFirma`) | — | — |
| Salir | `Login.dc.html` | — |
| Idioma (`UiIdioma`) | — | — siempre a la derecha |

## 4. Subnavegación

- **Decisiones** (dentro de la página, debajo de la cabecera): pestañas «Tratos» → `Estilo.dc.html` y
  «Cola de gate» → `Gate.dc.html`. Las dos pantallas muestran la misma pestaña activa.
- **Empresa** (`UiEmpresaNav`): «Reglas de decisión» → `Config`, «Datos financieros» → `OnbCSV`,
  «Cuentas de plataformas» → `OnbAlta`, «Firma y claves» → `Firma`, «Auditoría» → `Auditoria`.

## 5. Flujos

1. **Alta y activación de datos:** `OnbAlta` (pasos 1–6, pasos internos) → `OnbCSV` → `OnbResumen` →
   activación con passkey → `Mision`.
2. **Nueva misión:** `Mision` → «Nueva misión» → `Peticion` → «Lanzar misión» → `Mision`.
3. **Decisión de un trato:** `Mision` → «Ver comparativa» → `Comparativa` → «Decidir sobre Vendedor A» →
   `Estilo`. Desde Estilo, la cola de gate está en la pestaña «Cola de gate».
4. **Negociación:** `Mision` → «Abrir negociación» → `Negociacion` → «Volver a la misión» → `Mision`.

## 6. Guardas

Lo que bloquea o redirige. Los textos exactos de cada estado están en el lienzo (`Estados.dc.html`).

- Sin onboarding completo y snapshot financiero activo no se lanzan misiones. El lienzo no implementa aún
  esta guarda en «Nueva misión»; la propuesta es que lleve a `OnbCSV` cuando falte el snapshot.
- Datos financieros caducados: el aviso de la cabecera lleva a `OnbCSV`; bloquea la compra directa.
- Sesión de firma caducada o respuesta `428 reauth_required`: la pantalla pasa a modo lectura en la misma
  página, sin cambiar de ruta. Ver «Reautenticar para firmar» en la cabecera.
- Rol `viewer`: sin acciones de firma ni enlace a firma en la subnavegación de Empresa (pendiente de
  decidir si se oculta o se muestra deshabilitada).

## 7. Cabeceras de onboarding

`UiOnbCabecera` es una cabecera reducida (logo, texto de paso, idioma) que solo usaba `OnbResumen`.
Se retira en favor de `UiCabecera` + `UiEmpresaNav`. Si se reintroduce, documentar aquí por qué.

## 8. Pantallas fuera de la navegación de producto

Estas pantallas existen en el lienzo pero no tienen entrada desde la app. No son errores; son decisiones
pendientes.

| Archivo | Qué es | Pendiente |
|---|---|---|
| `Main.dc.html` | «Cola y tratos» con pestañas internas Cola/Tratos | Decidir si es la pantalla canónica de Decisiones (y si `Estilo` y `Gate` se unifican con ella) |
| `Login.dc.html` | Acceso (variante base) | Entrada desde el arranque de la app sin sesión; enlazada solo desde «Salir» |
| `LoginJirafa.dc.html`, `LoginRD.dc.html` | Variantes de exploración del acceso | Elegir una y borrar las demás |
| `Estados.dc.html`, `EstadosUI.dc.html` | Catálogo de estados y estados vacíos/errores | Solo documentación de diseño |
| `Sistema.dc.html` | Sistema visual | Solo documentación de diseño |
| `Plan.dc.html` | Plan de implementación DEV-6 | Solo documentación |
| `Carga.dc.html` | Indicador de carga a pantalla completa | Componente de exhibición; la app lo usa como `UiCargando` |
| `Ui*.dc.html` | Componentes compartidos | No son pantallas |

## 9. Cómo actualizar este documento

Al cambiar una pantalla o un enlace (en el lienzo o en código):

1. Actualiza la tabla de §2 si cambia una pantalla, su cabecera o su destino.
2. Actualiza §3 o §4 si cambia la cabecera o la subnavegación.
3. Actualiza §5 si cambia un flujo.
4. Quita de §8 las pantallas que ya tengan entrada, o añádelas si pierden una.
5. Añade una línea a «Registro de cambios».
6. Informa del cambio de navegación en la descripción del cambio, con enlace a este documento.

## Registro de cambios

- **2026-11-08:** primera versión. «Nueva misión» en Misiones → `Peticion`. Cola y tratos comparten
  pestañas. `Main` usa `UiCabecera`. Resumen del onboarding usa `UiCabecera` + `UiEmpresaNav`, con
  «Volver a revisar el CSV» y «Activar con passkey» → `Mision`. «Salir» en la cabecera → `Login`.
