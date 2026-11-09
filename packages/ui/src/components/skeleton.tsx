import { cn } from '../lib/utils.js'

/** Opacidad .6–1 en 1,6 s; sin brillo que recorre. Da la forma final con `className`. */
export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div aria-hidden="true" className={cn('bg-raised motion-safe:animate-[ap-pulso_1.6s_ease-in-out_infinite]', className)} {...props} />
}
