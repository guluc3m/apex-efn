import { cn } from '../lib/utils.js'

const SIZE = {
  sm: { w: 24, cls: 'gap-1.5 text-[17.28px]' },
  md: { w: 32, cls: 'gap-2 text-[23.04px]' },
  lg: { w: 64, cls: 'gap-4 text-[46.08px]' },
  xl: { w: 128, cls: 'gap-8 text-[92.16px]' },
} as const
const TONE = { onDark: 'text-ink', onLight: 'text-bg', soft: 'text-ink-soft' } as const

export interface LogoProps {
  size?: keyof typeof SIZE
  tone?: keyof typeof TONE
  variant?: 'logotipo' | 'isotipo'
  /** Con href es un enlace. */
  href?: string
  /** Nombre accesible; es la marca, no se traduce. */
  label?: string
  className?: string
}

/** `size` es el ancho del isotipo (retícula 64x40); texto al 72 % y separación de un cuarto. */
export function Logo({ size = 'sm', tone = 'onDark', variant = 'logotipo', href, label = 'APEX', className }: LogoProps) {
  const { w, cls: sizeCls } = SIZE[size]
  const body = (
    <>
      <svg viewBox="0 0 64 40" width={w} height={(w * 40) / 64} fill="currentColor" aria-hidden="true" className="block flex-none">
        <path d="M14 0H50L64 20 50.54 39.23 32 8.33 13.46 39.23 0 20Z" />
        <path d="M32 19.17 44.5 40H19.5Z" />
      </svg>
      {variant === 'logotipo' && (
        <span aria-hidden="true" className="-translate-y-[0.04em] pr-[0.04em]">
          apex
        </span>
      )}
    </>
  )
  const cls = cn(sizeCls, 'inline-flex items-center leading-none font-semibold tracking-[-0.04em] no-underline', TONE[tone], className)
  return href ? (
    <a href={href} aria-label={label} className={cls}>
      {body}
    </a>
  ) : (
    <span role="img" aria-label={label} className={cls}>
      {body}
    </span>
  )
}
