import { getRequestConfig } from 'next-intl/server'

// ponytail: un solo idioma y sin mensajes; añadir messages/<locale>.json al traducir la UI
export default getRequestConfig(() => ({ locale: 'es', messages: {} }))
