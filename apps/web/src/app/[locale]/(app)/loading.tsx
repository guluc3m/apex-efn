import { SphereLoader } from '@apex/ui'
import { getTranslations } from 'next-intl/server'

export default async function Loading() {
  const t = await getTranslations('shell')
  return (
    <div className="flex justify-center py-24">
      <SphereLoader label={t('loading')} />
    </div>
  )
}
