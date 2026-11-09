import type { FieldErrors, FieldValues, Resolver } from 'react-hook-form'
import { z } from 'zod'

export const STEP_IDS = ['empresa', 'sector', 'cuentas', 'presupuesto', 'politica', 'negociacion', 'finanzas'] as const
export type StepId = (typeof STEP_IDS)[number]

// Los mensajes son claves de `onboarding.errors.*`.
const req = z.string().trim().min(1, 'required')
const amount = z.string().trim().regex(/^\d[\d.,]*\s*(€|\$|¥)?$/, 'amount')
const percent = z.string().trim().regex(/^\d{1,3}([.,]\d+)?$/, 'percent')

const row = z.object({ id: z.string(), label: z.string() })

export const schemas = {
  empresa: z.object({ razonSocial: req, cif: req, pais: req, aduana: req, direccion: req, facturacionIgual: z.boolean() }),
  sector: z.object({ cnae: req, frecuencia: req, compras: req, estacionalidad: z.string() }),
  presupuesto: z.object({
    divisa: req,
    pago: req,
    colchon: percent,
    categorias: z.array(row.extend({ envelope: amount, maximo: amount })),
  }),
  politica: z.object({
    aprobacion: amount,
    doble: amount,
    confianza: req,
    plazo: req,
    certificaciones: z.array(z.string()),
    paisesExcluidos: z.string(),
    vetados: z.string(),
  }),
  negociacion: z.object({
    categorias: z.array(row.extend({ objetivo: percent, maximo: percent })),
    agresividad: req,
    tono: req,
    idioma: req,
    contrapartidas: z.array(z.string()),
  }),
}
export type FormStepId = keyof typeof schemas
export type Drafts = { [K in FormStepId]: z.infer<(typeof schemas)[K]> }

/** Resolver mínimo zod → RHF (evita una dependencia solo para esto). Primer error por campo. */
export function zodResolver<S extends z.ZodType<FieldValues, z.ZodTypeDef, FieldValues>>(schema: S): Resolver<z.infer<S>> {
  return (values) => {
    const r = schema.safeParse(values)
    if (r.success) return { values: r.data, errors: {} }
    const errors: Record<string, unknown> = {}
    for (const { path, message } of r.error.issues) {
      let node = errors
      path.forEach((key, i) => {
        if (i === path.length - 1) node[key] ??= { type: 'zod', message }
        else node = (node[key] ??= typeof path[i + 1] === 'number' ? [] : {}) as Record<string, unknown>
      })
    }
    return { values: {}, errors: errors as FieldErrors<z.infer<S>> }
  }
}
