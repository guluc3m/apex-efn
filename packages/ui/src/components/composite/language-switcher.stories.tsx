import type { Meta, StoryObj } from '@storybook/react'
import { useState } from 'react'

import { LanguageSwitcher } from './language-switcher.js'

const options = [
  { id: 'es', name: 'Español', code: 'ES', lang: 'es' },
  { id: 'en', name: 'English', code: 'EN', lang: 'en' },
  { id: 'zh', name: '简体中文', code: 'ZH', lang: 'zh-Hans' },
]

const meta = { title: 'Compuestos/LanguageSwitcher' } satisfies Meta
export default meta
type Story = StoryObj

export const Selector: Story = {
  render: () => {
    const [value, setValue] = useState('es')
    return (
      <LanguageSwitcher
        options={options}
        value={value}
        onChange={setValue}
        label="Idioma"
        menuLabel="Idioma de la interfaz"
      />
    )
  },
}
