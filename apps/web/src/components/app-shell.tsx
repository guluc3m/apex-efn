'use client'

import {
  AppHeader,
  CompanyNav,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Icon,
  Logo,
  type NavItem,
} from '@apex/ui'
import { Building2, ChevronDown, ClipboardCheck, FileSignature, Gavel, History, Landmark, LogOut, ScrollText, Target, UserRound, Wallet } from 'lucide-react'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

import { signOutAction } from '@/app/actions/sign-out'
import type { Viewer } from '@/lib/viewer'

import { AppLink, renderLink } from './app-link'
import { AppLanguageSwitcher } from './language-switcher'
import { ConnectedSigningIndicator } from './signing-indicator'

/** Ruta sin el prefijo de idioma. */
function useAppPath() {
  return '/' + usePathname().split('/').slice(2).join('/')
}

const isIn = (path: string, base: string) => path === base || path.startsWith(`${base}/`)

function UserMenu({ viewer }: { viewer: Viewer }) {
  const t = useTranslations('shell.userMenu')
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t('trigger')}
        className="group inline-flex h-9.5 cursor-pointer items-center gap-2 border border-line-strong bg-transparent pr-2.5 pl-3 text-[13px] text-ink transition-[border-color] duration-(--fast) hover:border-ink-muted"
      >
        <Icon icon={UserRound} className="text-ink-soft" />
        <span>{t(`roles.${viewer.role}`)}</span>
        <Icon icon={ChevronDown} className="text-ink-muted transition-transform duration-(--fast) ease-apex-move group-data-[state=open]:rotate-180 motion-reduce:transition-none" />
      </DropdownMenuTrigger>
      <DropdownMenuContent aria-label={t('menu')} className="w-64">
        <div className="px-3 pt-2 pb-2">
          <div className="font-medium">{t(`roles.${viewer.role}`)}</div>
          {viewer.tenantId && <div className="text-[13px] text-ink-muted">{viewer.tenantId}</div>}
        </div>
        <DropdownMenuItem icon={LogOut} onSelect={() => void signOutAction()}>
          {t('signOut')}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function AppShell({ children, viewer }: { children: ReactNode; viewer: Viewer }) {
  const t = useTranslations('shell')
  const path = useAppPath()
  const items: NavItem[] = [
    { label: t('nav.decisions'), href: '/decisiones', icon: Gavel, current: isIn(path, '/decisiones') },
    { label: t('nav.missions'), href: '/misiones', icon: Target, current: isIn(path, '/misiones') },
    { label: t('nav.approvals'), href: '/aprobaciones', icon: ClipboardCheck, current: isIn(path, '/aprobaciones') },
    { label: t('nav.company'), href: '/empresa/reglas', icon: Building2, current: isIn(path, '/empresa') },
  ]
  return (
    <>
      <AppHeader
        navLabel={t('nav.label')}
        skipLabel={t('skip')}
        items={items}
        renderLink={renderLink}
        brand={
          <AppLink href="/decisiones" aria-label={t('nav.home')} className="inline-flex items-center no-underline">
            <Logo size="sm" />
          </AppLink>
        }
        trailing={
          <>
            <ConnectedSigningIndicator />
            <AppLanguageSwitcher />
            <UserMenu viewer={viewer} />
          </>
        }
      />
      <main id="contenido" tabIndex={-1}>
        {children}
      </main>
    </>
  )
}

/** Subnavegación de /empresa/*; la monta app/[locale]/(app)/empresa/layout.tsx. */
export function CompanyShell({ children, role }: { children: ReactNode; role: Viewer['role'] }) {
  const t = useTranslations('shell.companyNav')
  const path = useAppPath()
  const items: NavItem[] = [
    { label: t('rules'), href: '/empresa/reglas', icon: ScrollText },
    { label: t('finance'), href: '/empresa/finanzas', icon: Wallet },
    { label: t('accounts'), href: '/empresa/cuentas', icon: Landmark },
    { label: t('signing'), href: '/empresa/firma', icon: FileSignature },
    ...(role === 'admin' || role === 'owner' ? [{ label: t('audit'), href: '/empresa/auditoria', icon: History }] : []),
  ].map((it) => ({ ...it, current: path === it.href }))
  return (
    <>
      <CompanyNav label={t('label')} items={items} renderLink={renderLink} />
      {children}
    </>
  )
}
