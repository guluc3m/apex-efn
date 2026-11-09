import { Icon } from '@apex/ui'
import { Circle, CircleCheck, LoaderCircle, type LucideIcon } from 'lucide-react'
import { useTranslations } from 'next-intl'

type PhaseState = 'done' | 'running' | 'pending'
interface Phase {
  id: string
  state: PhaseState
  values: Record<string, string | number>
}

const STATE: Record<PhaseState, { icon: LucideIcon; icon_cls: string; bar: string }> = {
  done: { icon: CircleCheck, icon_cls: 'text-good', bar: 'shadow-[inset_0_-2px_0_var(--accent)]' },
  running: { icon: LoaderCircle, icon_cls: 'text-ink-soft', bar: 'shadow-[inset_0_-2px_0_var(--ink-muted)]' },
  pending: { icon: Circle, icon_cls: 'text-ink-muted', bar: '' },
}

/** Fases de la misión: icono + color + texto, nunca solo color. */
export function MissionPhases({ phases }: { phases: readonly Phase[] }) {
  const t = useTranslations('missions.detail')
  return (
    <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(200px,1fr))] border-b border-line p-0" aria-label={t('phases.label')}>
      {phases.map((p, i) => (
        <li key={p.id} className={`px-gutter-panel py-4 first:px-gutter-page ${STATE[p.state].bar}`} aria-current={p.state === 'running' ? 'step' : undefined}>
          <div className="flex items-center gap-1.5 text-[13px] text-ink-muted">
            <span className={`flex ${STATE[p.state].icon_cls}`}>
              <Icon icon={STATE[p.state].icon} label={t(`phases.state.${p.state}`)} />
            </span>
            {i + 1} · {t(`phases.${p.id}.title`)}
          </div>
          <strong className="font-semibold">{t(`phases.${p.id}.${p.state}`, p.values)}</strong>
        </li>
      ))}
    </ol>
  )
}
