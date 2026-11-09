import { cn } from '../lib/utils.js'

export interface SphereLoaderProps {
  /** Qué se espera («Firmando decisión…»). Obligatorio: el indicador nunca va sin texto. */
  label: string
  className?: string
}

// ponytail: solo la ola de DESIGN §9.2; falta el intercambio por arcos entre parejas.
export function SphereLoader({ label, className }: SphereLoaderProps) {
  return (
    <div role="status" className={cn('inline-flex flex-col items-center gap-3 text-ink-soft', className)}>
      <div aria-hidden="true" className="flex h-12 items-end gap-3">
        {[0, 1, 2, 3].map((i) => (
          <span
            key={i}
            style={{ animationDelay: `${i * 120}ms` }}
            className="size-8 rounded-full bg-ink motion-safe:animate-[ap-bota_1.4s_var(--easing-move)_infinite]"
          />
        ))}
      </div>
      <span>{label}</span>
    </div>
  )
}
