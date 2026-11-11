# Guion · APEX-EFN en 7 minutos

Corte estático de 12 diapositivas + anexo. Se proyecta desde
`docs/entrega/presentacion-7min.pdf`. El anexo no se presenta: es esta hoja de ruta.

| #  | Diapositiva               | Desde–hasta | Seg. |
|----|---------------------------|-------------|------|
| 1  | Portada                   | 0:00–0:20   | 20   |
| 2  | El problema               | 0:20–0:55   | 35   |
| 3  | La propuesta: 8 pasos     | 0:55–1:35   | 40   |
| 4  | Tres invariantes          | 1:35–2:05   | 30   |
| 5  | Arquitectura              | 2:05–2:50   | 45   |
| 6  | Motores deterministas     | 2:50–3:25   | 35   |
| 7  | Confianza del vendedor    | 3:25–3:55   | 30   |
| 8  | Precio y gate             | 3:55–4:30   | 35   |
| 9  | Negociación               | 4:30–5:05   | 35   |
| 10 | Encaje financiero         | 5:05–5:35   | 30   |
| 11 | Decisión y firma          | 5:35–6:20   | 45   |
| 12 | Estado y cierre           | 6:20–7:00   | 40   |
|    | **Total**                 | **7:00**    | **420** |

---

## 1 · Portada (0:00–0:20)

- Abre con la frase, sin preámbulo: «El agente negocia. Tú decides.»
- Sitúa el problema en una línea: compras B2B por volumen, de la búsqueda a la firma verificable.
- Señala la tarjeta de la derecha: un trato con confianza, precio, encaje y firma pendiente. Es
  ilustrativo y lo dices.
- No expliques todavía los cuatro pasos del recorrido; están para que el jurado sepa dónde va esto.

## 2 · El problema (0:20–0:55)

- El precio real no está publicado: se negocia por chat, vendedor a vendedor, y sin tiempo se paga
  el de lista.
- Lo más barato es lo más peligroso: precios gancho, falsificaciones y reseñas infladas.
- El precio de lista no es el coste: faltan envío, aranceles, IVA de importación, divisa y capital.
- Cierra con la cuarta: nadie puede demostrar qué se decidió ni con qué datos.

## 3 · La propuesta: 8 pasos (0:55–1:35)

- Recorre el pipeline de izquierda a derecha: perfila, busca, confianza, precio, regatea, encaje,
  decide, firma.
- Marca el corte: perfilado y búsqueda son IA y código; confianza, precio y encaje son código;
  decidir y firmar son persona.
- Di la regla: ningún paso se salta. Una oferta con precio anómalo o poca confianza no llega a
  regatear.
- Remata: la IA donde aporta; los números, en código determinista.

## 4 · Tres invariantes (1:35–2:05)

- La confianza se calcula, no se opina: antigüedad, ventas, catálogo y reseñas, con banda y versión
  del modelo en cada oferta.
- El precio se filtra antes de negociar: cero presupuesto de negociación en ofertas anómalas.
- Sin firma humana no hay compromiso: Ed25519 en el navegador, la clave privada no sale del
  dispositivo.
- Si una falla, la oferta no avanza; no se compensa con las otras.

## 5 · Arquitectura (2:05–2:50)

- Cuatro piezas: web Next.js con BFF, orquestador FastAPI y LangGraph, browser worker y la capa de
  datos.
- Nombra los agentes sin entrar en cada uno: Intake, Planner, Enrichment, Gate, Evaluator,
  Supervisor y el negociador.
- El worker hace scraping y chat, y se queda las credenciales: el orquestador y el LLM solo ven un
  `account_id`.
- Baja a la pasarela: compatible OpenAI `/v1/chat/completions`, con vLLM, llama.cpp u Ollama.
  Modelos autoalojados, sin SDK propietario.
- Si preguntan por aislamiento: Postgres con RLS por tenant y S3 con Object Lock.

## 6 · Motores deterministas (2:50–3:25)

- Son seis cálculos y ninguno llama a un modelo: dinero y FX, CSV y landed cost, confianza, sanidad
  de precio, matriz de gate y ranking MCDA.
- Dinero en céntimos enteros y tipos de cambio decimales; la suma del coste cuadra al céntimo.
- Confianza, precio y gate llevan `config_version` o `model_version`: el mismo snapshot y la misma
  config dan el mismo resultado.
- TypeScript y Python pasan los mismos vectores. Esa es la garantía de que la UI y las decisiones
  no divergen.

## 7 · Confianza del vendedor (3:25–3:55)

- Explica las cuatro piezas: normalización saturada con `x_sat` por señal, suavizado bayesiano, cota
  inferior de Wilson y flags de manipulación.
- Un flag estructural (ráfagas, 5 estrellas anómalas, texto duplicado) capa la banda en `low`.
- Pocas señales no es poca confianza: es `insufficient_data`. El sistema lo dice en vez de inventar.
- Contrasta las dos tarjetas: 1 reseña de 5,0 da 38; 500 de 4,8 dan 86. Mismo config, misma versión.
  Son cifras ilustrativas.

## 8 · Precio y gate (3:55–4:30)

- Referencia robusta: mediana y MAD, con fallback a IQR. Bandas asimétricas: el lado barato es más
  estricto.
- Un precio más de un 60 % por debajo de la mediana es al menos `atypical`; la confianza alta no lo
  compensa.
- Sin referencia suficiente (`insufficient_reference`) no se negocia: va al gate.
- Recorre la matriz 3×3 y detente en atípico + confianza baja: escala a descarte. Y en la nota:
  negociación, cero llamadas en atípico e implausible.

## 9 · Negociación (4:30–5:05)

- Playbook de seis pasos: contexto, ancla justificada, pedir volumen, escalera de contraofertas,
  detectar cierre y resumen por escrito.
- El LLM redacta y extrae la oferta; los límites están en código y se comprueban antes de enviar.
- Guardrails: `max_discount`, tope de rondas y tokens, nada de prepago ni garantías no autorizadas,
  y pago fuera de plataforma o datos sensibles se escalan a una persona.
- Fase 1 semiautomática: cada mensaje espera aprobación. Takeover humano: el agente no envía
  mientras una persona tiene el control.

## 10 · Encaje financiero (5:05–5:35)

- No se compara el precio de lista con la caja: se compara el coste total.
- Recorre el desglose: mercancía, envío, seguro, aranceles, IVA de importación, coste de capital y
  FX. Todo suma 10.103,00 €; el precio de lista eran 8.000,00 €.
- El veredicto sale contra el presupuesto y la tesorería: `within_budget`, `stretch` u
  `out_of_budget`, con el motivo numérico.
- Di que los importes son ilustrativos y que las tasas salen de config, nunca de una constante.

## 11 · Decisión y firma (5:35–6:20)

- La ficha del trato lleva todo lo que hace falta para decidir: confianza, precio, encaje y firma
  pendiente. Cada acción se firma.
- La firma: JSON canónico (RFC 8785), Ed25519 en el navegador, cadena de hashes por tenant y S3
  Object Lock en modo compliance.
- La ventana es fija: 15 minutos que firmar no alarga. Importe alto exige reautenticación inmediata;
  por encima del umbral, doble control con dos firmantes distintos.
- La cadena de hashes es lo que permite demostrar después qué se firmó y con qué datos.

## 12 · Estado y cierre (6:20–7:00)

- Ya funciona: onboarding con CSV activable, dos plataformas simuladas con chat, motores en TS y
  Python con vectores compartidos, gate y dashboard, firma, negociación semiautomática, RLS y
  auditoría WORM.
- Siguiente: adaptadores reales y envío autónomo en F2, calibración, ClickHouse y dbt, sellado
  RFC 3161, modelos autoalojados en producción, SSO empresarial y PSD2.
- Números: 6 lanes, 11 jobs de CI local, 6 imágenes, 1.687 tests Python; cobertura 99,6 % en money,
  98,1 % en crypto y 78,1 % en scoring (ratchet); cero marketplaces reales en CI.
- Cierra con la frase: «La IA negocia. El código calcula. Una persona firma.»

---

**Total: 7:00.** Si el tiempo aprieta, se recorta el bloque de motores (diapositiva 6, 35 s),
nunca la firma. Los datos de las diapositivas 1, 7 y 10 son ilustrativos y están etiquetados
como tales.
