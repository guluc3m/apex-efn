import { Check, ChevronDown, Globe } from 'lucide-react'

import { cn } from '../../lib/utils.js'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '../dropdown-menu.js'
import { Icon } from '../icon.js'

export interface LanguageOption {
  id: string
  /** Endónimo: cada idioma con su nombre en su propio idioma. */
  name: string
  /** Código corto del botón: ES, EN, ZH. */
  code: string
  /** Atributo `lang` BCP 47 de la opción (zh-Hans). */
  lang: string
}

export interface LanguageSwitcherProps {
  options: LanguageOption[]
  value: string
  /** Navegar a la misma página en otro idioma lo decide quien lo monta. */
  onChange: (id: string) => void
  /** Nombre accesible del botón, ya con el idioma actual. */
  label: string
  menuLabel: string
  className?: string
}

export function LanguageSwitcher({ options, value, onChange, label, menuLabel, className }: LanguageSwitcherProps) {
  const current = options.find((o) => o.id === value) ?? options[0]
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={label}
        className={cn(
          'group inline-flex h-9.5 cursor-pointer items-center gap-2 border border-line-strong bg-transparent pr-2.5 pl-3 text-[13px] text-ink transition-[border-color] duration-(--fast) hover:border-ink-muted',
          className,
        )}
      >
        <Icon icon={Globe} className="text-ink-soft" />
        <span className="font-mono tracking-[0.06em]">{current?.code}</span>
        <Icon icon={ChevronDown} className="text-ink-muted transition-transform duration-(--fast) ease-apex-move group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
      </DropdownMenuTrigger>
      <DropdownMenuContent aria-label={menuLabel} className="w-58">
        <div className="px-3 pt-2 pb-1.5 text-[13px] text-ink-muted">{menuLabel}</div>
        {options.map((o) => (
          <DropdownMenuItem key={o.id} lang={o.lang} aria-current={o.id === value ? 'true' : undefined} onSelect={() => onChange(o.id)}>
            <span className="inline-flex w-4 flex-none">{o.id === value && <Icon icon={Check} />}</span>
            <span className={cn('flex-1', o.id === value && 'font-medium')}>{o.name}</span>
            <span className="font-mono text-[13px] tracking-[0.06em] text-ink-muted">{o.code}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
