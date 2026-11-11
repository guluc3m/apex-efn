import { Button, Icon } from '@apex/ui'
import { Plus } from 'lucide-react'
import { getTranslations, setRequestLocale } from 'next-intl/server'
import { Suspense } from 'react'

import { AppLink } from '@/components/app-link'
import { MissionsList } from '@/components/missions/missions-list'

export default async function MissionsPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params
  setRequestLocale(locale)
  const t = await getTranslations('missions.list')

  return (
    <div className="flex flex-col gap-4 px-gutter-page py-gutter-panel">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight">{t('title')}</h1>
          <p className="text-ink-soft">{t('subtitle')}</p>
        </div>
        <Button variant="pri" asChild>
          <AppLink href="/misiones/nueva">
            <Icon icon={Plus} />
            {t('new')}
          </AppLink>
        </Button>
      </div>
      <Suspense>
        <MissionsList />
      </Suspense>
    </div>
  )
}
