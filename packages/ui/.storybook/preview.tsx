import type { Decorator, Preview } from '@storybook/react'

import './preview.css'

/** Idioma de la story: los textos llegan por props, así que cada story lee `locale` de aquí. */
const withDark: Decorator = (Story) => (
  <div className="bg-bg text-ink min-h-24 p-6">
    <Story />
  </div>
)

const preview: Preview = {
  decorators: [withDark],
  parameters: {
    layout: 'fullscreen',
    backgrounds: { disable: true },
    controls: { expanded: true },
    // Solo modo oscuro (DESIGN §1). Las violaciones serious/critical rompen el test de axe (src/test/axe.test.tsx).
    a11y: { test: 'error' },
  },
  globalTypes: {
    locale: {
      description: 'Idioma de la interfaz',
      toolbar: { icon: 'globe', items: ['es', 'en', 'zh'], dynamicTitle: true },
    },
  },
  initialGlobals: { locale: 'es' },
}

export default preview
