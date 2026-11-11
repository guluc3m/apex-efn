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
import {
  Building2,
  ChevronDown,
  ClipboardCheck,
  FileSignature,
  Gavel,
  History,
  Landmark,
  LogOut,
  ScrollText,
  Sparkles,
  Target,
  UserRound,
  Wallet,
} from 'lucide-react'
import { usePathname } from 'next/navigation'
import { useTranslations } from 'next-intl'
import type { ReactNode } from 'react'

import { signOutAction } from '@/app/actions/sign-out'
import { api } from '@/lib/api'
import { signOutWithCleanup } from '@/lib/signing/sign-out'
import type { Viewer } from '@/lib/viewer'
import { useSigningSession } from '@/stores/signing-session'

import { AppLink, renderLink } from './app-link'
import { AppLanguageSwitcher } from './language-switcher'
import { ConnectedSigningIndicator } from './signing-indicator'
import { ViewerProvider } from './viewer-context'

/** Ruta sin el prefijo de idioma. */
function useAppPath() {
  return '/' + usePathname().split('/').slice(2).join('/')
}

const isIn = (path: string, base: string) => path === base || path.startsWith(`${base}/`)

function UserMenu({ viewer }: { viewer: Viewer }) {
  const t = useTranslations('shell.userMenu')
  const session = useSigningSession((s) => s.session)
  // Logout closes the 15-minute signing window on this device first (issue #272, item 2). It is
  // best-effort: `signOutWithCleanup` swallows a failed DELETE and still logs out.
  const handleSignOut = () =>
    signOutWithCleanup({
      activeSessionId: session?.id ?? null,
      closeSession: (id) => api.closeSigningSession(id),
      clearLocal: () => useSigningSession.getState().clear(),
      signOut: signOutAction,
    })
  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        aria-label={t('trigger')}
        className="group border-line-strong text-ink hover:border-ink-muted inline-flex h-9.5 cursor-pointer items-center gap-2 border bg-transparent pr-2.5 pl-3 text-[13px] transition-[border-color] duration-(--fast)"
      >
        <Icon icon={UserRound} className="text-ink-soft" />
        <span>{t(`roles.${viewer.role}`)}</span>
        <Icon
          icon={ChevronDown}
          className="text-ink-muted ease-apex-move transition-transform duration-(--fast) group-data-[state=open]:rotate-180 motion-reduce:transition-none"
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent aria-label={t('menu')} className="w-64">
        <div className="px-3 pt-2 pb-2">
          <div className="font-medium">{t(`roles.${viewer.role}`)}</div>
          {viewer.tenantId && <div className="text-ink-muted text-[13px]">{viewer.tenantId}</div>}
        </div>
        <DropdownMenuItem icon={LogOut} onSelect={() => void handleSignOut()}>
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
    {
      label: t('nav.decisions'),
      href: '/decisiones',
      icon: Gavel,
      current: isIn(path, '/decisiones'),
    },
    { label: t('nav.missions'), href: '/misiones', icon: Target, current: isIn(path, '/misiones') },
    {
      label: t('nav.approvals'),
      href: '/aprobaciones',
      icon: ClipboardCheck,
      current: isIn(path, '/aprobaciones'),
    },
    {
      label: t('nav.company'),
      href: '/empresa/reglas',
      icon: Building2,
      current: isIn(path, '/empresa'),
    },
  ]
  return (
    <ViewerProvider viewer={viewer}>
      <AppHeader
        navLabel={t('nav.label')}
        skipLabel={t('skip')}
        items={items}
        renderLink={renderLink}
        brand={
          <AppLink
            href="/decisiones"
            aria-label={t('nav.home')}
            className="inline-flex items-center no-underline"
          >
            <Logo size="sm" />
          </AppLink>
        }
        trailing={
          <>
            <ConnectedSigningIndicator {...(viewer.userId ? { userId: viewer.userId } : {})} />
            <AppLanguageSwitcher />
            <UserMenu viewer={viewer} />
          </>
        }
      />
      <main id="contenido" tabIndex={-1}>
        {children}
      </main>
    </ViewerProvider>
  )
}

/** Subnavegación de /empresa/*; la monta app/[locale]/(app)/empresa/layout.tsx. */
export function CompanyShell({ children, role }: { children: ReactNode; role: Viewer['role'] }) {
  const t = useTranslations('shell.companyNav')
  const path = useAppPath()
  const items: NavItem[] = [
    { label: t('rules'), href: '/empresa/reglas', icon: ScrollText },
    { label: t('provider'), href: '/empresa/proveedor', icon: Sparkles },
    { label: t('finance'), href: '/empresa/finanzas', icon: Wallet },
    { label: t('accounts'), href: '/empresa/cuentas', icon: Landmark },
    { label: t('signing'), href: '/empresa/firma', icon: FileSignature },
    ...(role === 'admin' || role === 'owner'
      ? [{ label: t('audit'), href: '/empresa/auditoria', icon: History }]
      : []),
  ].map((it) => ({ ...it, current: path === it.href }))
  return (
    <>
      <CompanyNav label={t('label')} items={items} renderLink={renderLink} />
      {children}
    </>
  )
}
