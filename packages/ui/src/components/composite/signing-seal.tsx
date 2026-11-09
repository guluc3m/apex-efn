import * as React from 'react'

import { cn } from '../../lib/utils.js'

export interface SigningSealProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Dispara los 600 ms una vez. Solo desde estado simulado de fixture hasta que haya firma real. */
  // //todo_#150: activar con la confirmación real de la API de firmas
  playing: boolean
}

/**
 * El único momento coreografiado (DESIGN §8): una línea de 1 px recorre el contenedor de izquierda a
 * derecha; los hijos con la clase `ap-hash` se revelan con un recorte. Con movimiento reducido no hay efecto.
 */
export function SigningSeal({ playing, className, ...props }: SigningSealProps) {
  return <div data-seal={playing} className={cn('ap-seal relative', className)} {...props} />
}
