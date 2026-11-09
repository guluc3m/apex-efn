import * as React from 'react'

export interface LinkRenderProps {
  href: string
  className?: string
  children: React.ReactNode
  'aria-current'?: 'page'
}

/** Permite inyectar el `<Link>` del router sin que @apex/ui dependa de `next/*`. */
export type RenderLink = (props: LinkRenderProps) => React.ReactElement

export const anchor: RenderLink = ({ children, ...props }) => <a {...props}>{children}</a>
