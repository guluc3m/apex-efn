'use client'

import { Button, Icon, Select } from '@apex/ui'
import { Download } from 'lucide-react'
import { useTranslations } from 'next-intl'
import { useState } from 'react'

import { api } from '@/lib/api'

const FORMATS = ['pdf', 'csv', 'json'] as const
type Format = (typeof FORMATS)[number]

/** The server builds the document; the browser only saves the bytes it returns. */
export function ExportButton({ missionId, profile }: { missionId: string; profile: string }) {
  const t = useTranslations('compare')
  const [format, setFormat] = useState<Format>('pdf')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (): Promise<void> => {
    setBusy(true)
    setError(null)
    try {
      const blob = await api.exportMissionRecommendation(missionId, profile, format)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `recommendation-${missionId}.${format}`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-end gap-2">
        <Select
          label={t('exportFormat')}
          className="w-28"
          value={format}
          options={FORMATS.map((f) => ({ value: f, label: f.toUpperCase() }))}
          onValueChange={(v) => setFormat(v as Format)}
        />
        <Button variant="sec" onClick={() => void run()} disabled={busy}>
          <Icon icon={Download} label="" /> {t('export')}
        </Button>
      </div>
      {error && (
        <p role="alert" className="m-0 text-[13px] text-bad">
          {t('exportFailed', { reason: error })}
        </p>
      )}
    </div>
  )
}
