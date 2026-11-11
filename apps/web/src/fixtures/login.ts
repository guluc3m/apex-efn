// Muestra ilustrativa de la «Cola de decisión» del lienzo de acceso (no son datos reales: esta pantalla no tiene sesión).
export interface LoginSampleDeal {
  id: 'ready' | 'lowBand'
  product: string
  seller: string
  price: string
  score: number
  confidence: 'high' | 'low'
  /** Solo la tarjeta en banda baja lleva SLA, ya calculado por la API. */
  sla?: string
}

export const loginSampleDeals: readonly LoginSampleDeal[] = [
  { id: 'ready', product: 'Rodamiento 6204-2RS · 5.000 ud', seller: 'A', price: '1,72 €/ud', score: 86, confidence: 'high' },
  { id: 'lowBand', product: 'Válvula de bola DN25 · 800 ud', seller: 'B', price: '12,40 €/ud', score: 38, confidence: 'low', sla: '05:20' },
]
