import '@testing-library/jest-dom/vitest'

// jsdom no trae ResizeObserver ni matchMedia, que usan Radix y Tabs.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver ??= RO as unknown as typeof ResizeObserver
globalThis.matchMedia ??= ((q: string) => ({
  matches: false,
  media: q,
  addEventListener() {},
  removeEventListener() {},
  addListener() {},
  removeListener() {},
  onchange: null,
  dispatchEvent: () => false,
})) as unknown as typeof matchMedia
const proto = Element.prototype as unknown as Record<string, unknown>
proto.scrollIntoView ??= () => {}
proto.hasPointerCapture ??= () => false
