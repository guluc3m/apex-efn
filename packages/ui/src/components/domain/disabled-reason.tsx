import * as React from 'react'

import { Tooltip } from '../tooltip.js'

interface ControlProps {
  'aria-describedby'?: string
  'aria-disabled'?: boolean
  disabled?: boolean
  onClick?: React.MouseEventHandler
}

export interface DisabledReasonProps {
  /** Motivo que devuelve la API. Sin motivo, el control se renderiza tal cual. */
  reason?: string
  /** Un único control. Se queda enfocable (aria-disabled) para que el motivo llegue por teclado. */
  children: React.ReactElement<ControlProps>
}

/** Control inerte con motivo visible: el tooltip se abre al foco o al pasar el ratón. */
export function DisabledReason({ reason, children }: DisabledReasonProps) {
  if (!reason) return children
  const control = React.cloneElement(children, {
    disabled: undefined,
    'aria-disabled': true,
    onClick: (e: React.MouseEvent) => e.preventDefault(),
  })
  return <Tooltip text={reason}>{control}</Tooltip>
}
