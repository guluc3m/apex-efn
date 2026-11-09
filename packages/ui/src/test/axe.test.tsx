/// <reference types="vite/client" />
import { composeStories } from '@storybook/react'
import type { Meta, StoryFn } from '@storybook/react'
import { cleanup, render } from '@testing-library/react'
import axe from 'axe-core'
import type React from 'react'
import { afterEach, describe, expect, it } from 'vitest'

/**
 * Test de axe de todas las stories (DESIGN §11 y §12): cada componente llega con story y esta prueba la recorre.
 * Bloquean `serious` y `critical`. jsdom no calcula estilos, así que `color-contrast` se omite aquí y lo
 * comprueba el addon a11y de Storybook en el navegador.
 */
const modules = import.meta.glob<{ default: Meta } & Record<string, unknown>>(
  '../**/*.stories.tsx',
  { eager: true }
)

afterEach(cleanup)

describe.each(Object.entries(modules))('%s', (path, mod) => {
  const stories = composeStories(mod as never) as Record<string, StoryFn>
  it.each(Object.entries(stories))(
    '%s no tiene violaciones serias de axe',
    async (_name, Story) => {
      const Comp = Story as unknown as React.FC
      const { container } = render(<Comp />)
      const result = await axe.run(container, { rules: { 'color-contrast': { enabled: false } } })
      const bad = result.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical')
      expect(
        bad.map((v) => `${v.id}: ${v.help} (${v.nodes.length})`),
        path
      ).toEqual([])
    }
  )
})
