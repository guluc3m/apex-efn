/**
 * Campo de puntos hexagonal del acceso (LoginRD). Port literal del script del lienzo,
 * sin la simulación (estado `busy` y onda `ripple`). Determinista: semilla fija.
 */
type Stop = readonly [number, number, number, number]

// Paleta en el tono del acento (#8fbb8b en 0.78, #a0c99c en 0.92): sombra -> acento -> reflejo pálido.
const STOPS: readonly Stop[] = [
  [0, 20, 32, 22],
  [0.2, 38, 58, 40],
  [0.4, 66, 94, 66],
  [0.6, 104, 140, 102],
  [0.78, 143, 187, 139],
  [0.92, 160, 201, 156],
  [1, 214, 232, 212],
]
const L = 40
const CELL = 9
const RH = (CELL * Math.sqrt(3)) / 2

type Seg = readonly [number, number, number, number, number, number]
type Tip = readonly [number, number, number]

const ih = (a: number, b: number): number => {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263)) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296
}
const ss = (a: number, b: number, x: number): number => {
  const t = Math.max(0, Math.min(1, (x - a) / (b - a)))
  return t * t * (3 - 2 * t)
}
const clamp01 = (x: number): number => Math.max(0, Math.min(1, x))

export class LoginField {
  hoverT = 0
  private hover = 0
  private ph = 0
  private wx = 0
  private raf = 0
  private ro: ResizeObserver | undefined
  private revealK = 1
  private W = 0
  private H = 0
  private dpr = 1
  private cols = 0
  private rows = 0
  private G = new Float32Array(0)
  private F = new Float32Array(0)
  private T = new Float32Array(0)
  private S = new Float32Array(0)
  private CX = new Float32Array(0)
  private CY = new Float32Array(0)
  private nb = new Int32Array(0)
  private pal: string[] = []
  private palM: string[][] = [[], [], [], []]

  constructor(private readonly cv: HTMLCanvasElement) {}

  private g(i: number): number {
    return this.G[i] ?? 0
  }

  private noise(x: number, y: number): number {
    const xi = Math.floor(x)
    const yi = Math.floor(y)
    const fx = x - xi
    const fy = y - yi
    const u = fx * fx * (3 - 2 * fx)
    const v = fy * fy * (3 - 2 * fy)
    const y0 = (yi & 255) << 8
    const y1 = ((yi + 1) & 255) << 8
    const x0 = xi & 255
    const x1 = (xi + 1) & 255
    const a = this.g(y0 | x0)
    const b = this.g(y0 | x1)
    const c = this.g(y1 | x0)
    const d = this.g(y1 | x1)
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v
  }

  /** Rejilla hexagonal + árbol. */
  private setup(): void {
    const cv = this.cv
    const parent = cv.parentElement
    if (!parent) return
    const box = parent.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    this.W = box.width
    this.H = box.height
    this.dpr = dpr
    cv.width = Math.max(1, Math.round(box.width * dpr))
    cv.height = Math.max(1, Math.round(box.height * dpr))
    const cols = Math.ceil(box.width / CELL) + 4
    let rows = Math.ceil(box.height / RH) + 4
    if (rows % 2) rows += 1
    this.cols = cols
    this.rows = rows
    const n = cols * rows
    if (n < 6) return

    let seed = 20261108
    const rnd = (): number => {
      seed = (seed * 1664525 + 1013904223) >>> 0
      return seed / 4294967296
    }

    this.G = new Float32Array(65536)
    for (let i = 0; i < 65536; i++) this.G[i] = rnd()
    this.F = new Float32Array(n)
    this.T = new Float32Array(n)
    this.S = new Float32Array(n)
    this.CX = new Float32Array(n)
    this.CY = new Float32Array(n)

    const nb = new Int32Array(n * 6)
    const w = (c: number, r: number): number => ((r + rows) % rows) * cols + ((c + cols) % cols)
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const k = r * cols + c
        const i = k * 6
        const o = r & 1
        nb[i] = w(c - 1, r)
        nb[i + 1] = w(c + 1, r)
        nb[i + 2] = w(c - 1 + o, r - 1)
        nb[i + 3] = w(c + o, r - 1)
        nb[i + 4] = w(c - 1 + o, r + 1)
        nb[i + 5] = w(c + o, r + 1)
        this.CX[k] = (c + 0.5 + 0.5 * o) * CELL + (box.width - cols * CELL) / 2
        this.CY[k] = (r + 0.5) * RH + (box.height - rows * RH) / 2
      }
    }
    this.nb = nb

    this.pal = []
    for (let l = 0; l < L; l++) {
      const s = l / (L - 1)
      let j = 0
      while (j < STOPS.length - 2 && s > (STOPS[j + 1]?.[0] ?? 1)) j++
      const a = STOPS[j] ?? STOPS[0]!
      const b = STOPS[j + 1] ?? a
      const f = (s - a[0]) / (b[0] - a[0])
      this.pal.push(
        `rgb(${Math.round(a[1] + (b[1] - a[1]) * f)},${Math.round(a[2] + (b[2] - a[2]) * f)},${Math.round(a[3] + (b[3] - a[3]) * f)})`,
      )
    }

    // Variantes con tinte frío para el cielo (4 niveles de mezcla).
    this.palM = [[], [], [], []]
    for (let l = 0; l < L; l++) {
      const rgb = (this.pal[l] ?? '').match(/\d+/g)?.map(Number) ?? [0, 0, 0]
      const s = l / (L - 1)
      const cr = 14 + 150 * Math.pow(s, 1.2)
      const cg = 30 + 170 * s
      const cb = 26 + 148 * s
      for (let m = 0; m < 4; m++) {
        const f = (m / 3) * 0.8
        const [r0 = 0, g0 = 0, b0 = 0] = rgb
        this.palM[m]?.push(
          `rgb(${Math.round(r0 + (cr - r0) * f)},${Math.round(g0 + (cg - g0) * f)},${Math.round(b0 + (cb - b0) * f)})`,
        )
      }
    }

    this.buildTree(rnd)
  }

  /** Silueta de árbol: tronco, ramas recursivas y copas, en una máscara de oscuridad por celda. */
  private buildTree(rnd: () => number): void {
    const { W, H, CX, CY, T } = this
    const segs: Seg[] = []
    const tips: Tip[] = []
    const grow = (x: number, y: number, ang: number, len: number, th: number, depth: number): void => {
      const x2 = x + Math.sin(ang) * len
      const y2 = y - Math.cos(ang) * len
      const th2 = th * 0.74
      segs.push([x, y, x2, y2, th, th2])
      if (depth === 0) {
        tips.push([x2, y2, len])
        return
      }
      grow(x2, y2, ang + (rnd() - 0.5) * 0.4, len * 0.84, th2, depth - 1)
      const sides = depth > 3 ? 2 : rnd() < 0.7 ? 1 : 0
      for (let s = 0; s < sides; s++) {
        const dir = (s === 0 ? -1 : 1) * (rnd() < 0.5 ? 1 : -1)
        grow(x2, y2, ang + dir * (0.5 + rnd() * 0.5), len * (0.62 + rnd() * 0.12), th2 * 0.78, depth - 1)
      }
    }
    grow(W * 0.46, H * 1.06, -0.1, H * 0.22, Math.max(26, W * 0.07), 7)
    for (let i = 0; i < T.length; i++) {
      const x = CX[i] ?? 0
      const y = CY[i] ?? 0
      let m = 0
      for (const g of segs) {
        const dx = g[2] - g[0]
        const dy = g[3] - g[1]
        const t = Math.max(0, Math.min(1, ((x - g[0]) * dx + (y - g[1]) * dy) / (dx * dx + dy * dy)))
        const d = Math.hypot(x - (g[0] + dx * t), y - (g[1] + dy * t))
        const half = (g[4] + (g[5] - g[4]) * t) * 0.5
        const blur = 14 + half * 1.1
        if (d > half + blur) continue
        m = Math.max(m, 1 - ss(half * 0.6, half + blur, d))
      }
      for (const g of tips) {
        const d = Math.hypot(x - g[0], y - g[1])
        const rad = g[2] * 1.5
        if (d < rad) m = Math.max(m, 0.55 * (1 - ss(0, rad, d)))
      }
      T[i] = m
    }
  }

  /** "Fragment shader": un valor 0..1 por celda. */
  private shade(t: number, wx: number, sway: number): void {
    const { cols, rows, CX, CY, T, F, S, W, H } = this
    for (let r = 0; r < rows; r++) {
      const amp = sway * (0.2 + 0.8 * (1 - r / rows))
      const sw = Math.sin(t * 0.7 + r * 0.03) * amp + Math.sin(t * 1.9 + r * 0.09) * amp * 0.25
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c
        const x = CX[i] ?? 0
        const y = CY[i] ?? 0
        // Estrías horizontales de desenfoque de movimiento.
        const nx = (x + wx * 26) / (CELL * 30)
        const ny = y / (CELL * 2.8)
        const n =
          0.58 * this.noise(nx, ny) + 0.28 * this.noise(nx * 2.1 + 5.3, ny * 2.2 + 1.7) + 0.14 * this.noise(nx * 4.4 + 9.1, ny * 4.1 + 3.3)
        const lo = this.noise(x / (W * 0.45) + wx * 0.02, y / (H * 0.28) + 7.7)
        let s = 0.66 + 0.62 * (n - 0.5) - 0.25 * ss(0.52, 0.8, lo)
        // Sombra del árbol con vaivén (más arriba, más movimiento).
        let fc = c + sw
        fc = Math.max(0, Math.min(cols - 1.001, fc))
        const c0 = Math.floor(fc)
        const fr = fc - c0
        const tk = (T[r * cols + c0] ?? 0) * (1 - fr) + (T[r * cols + c0 + 1] ?? 0) * fr
        s = s * (1 - 0.5 * tk) - 0.03 * tk * n
        s *= 1 - 0.12 * (y / H) * (y / H)
        if (n > 0.8) s += (n - 0.8) * 1.5 * (1 - tk)
        F[i] = s
        S[i] = clamp01((1 - y / (H * 0.75)) * (0.55 + 0.9 * lo) * (1 - 0.8 * tk))
      }
    }
  }

  private frame(t: number): void {
    const ctx = this.cv.getContext('2d')
    if (!ctx) return
    const { rows, cols, F, nb, CX, CY, W, H, ph } = this
    this.shade(t, this.wx, 2.2 + 1.5 * this.hover)
    ctx.setTransform(this.dpr, 0, 0, this.dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    const rev = this.revealK
    const swapP = 0.55 + 0.2 * this.hover
    const paths: Path2D[] = []
    for (let l = 0; l < L * 4; l++) paths.push(new Path2D())
    for (let r = 0; r < rows; r++) {
      const cy = CY[r * cols] ?? 0
      if (cy > H + CELL) break
      if (cy > rev * (H + CELL)) break
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c
        const hs = ih(i, 77)
        const u = ph + hs * 17
        const q = Math.floor(u)
        const fq = u - q
        // Intercambio de color con un vecino (favorece izquierda/derecha para mantener las estrías).
        let v = F[i] ?? 0
        const h1 = ih(i, q)
        if (h1 < swapP) {
          const k = Math.min(5, Math.floor(ih(i, q + 4099) * 8))
          const j = k < 4 ? k & 1 : k - 2
          const m = ss(0, 0.15, fq) * (1 - ss(0.85, 1, fq))
          v += ((F[nb[i * 6 + j] ?? 0] ?? 0) - v) * m
        }
        v += (ih(i, q + 7) + (ih(i, q + 8) - ih(i, q + 7)) * ss(0, 1, fq) - 0.5) * 0.12
        const l = Math.max(0, Math.min(L - 1, Math.round(v * (L - 1))))
        const m2 = Math.round(clamp01(this.S[i] ?? 0) * 3)
        const p = paths[m2 * L + l]
        const cx = CX[i] ?? 0
        p?.moveTo(cx + CELL * 0.3, cy)
        p?.arc(cx, cy, CELL * 0.3, 0, 6.2832)
      }
    }
    for (let k = 0; k < L * 4; k++) {
      const path = paths[k]
      const fill = this.palM[Math.floor(k / L)]?.[k % L]
      if (path && fill) {
        ctx.fillStyle = fill
        ctx.fill(path)
      }
    }
  }

  private still(): void {
    this.revealK = 1
    this.ph = 3.3
    this.wx = 1.5
    if (this.F.length) this.frame(2)
  }

  start(): void {
    cancelAnimationFrame(this.raf)
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    this.setup()
    const parent = this.cv.parentElement
    if (typeof ResizeObserver !== 'undefined' && !this.ro && parent) {
      let first = true
      this.ro = new ResizeObserver(() => {
        if (first) {
          first = false
          return
        }
        this.setup()
        if (reduce) this.still()
      })
      this.ro.observe(parent)
    }
    if (reduce) {
      this.still()
      return
    }
    let t0 = 0
    let prev = 0
    const tick = (now: number): void => {
      if (!t0) {
        t0 = now
        prev = now
      }
      const t = (now - t0) / 1000
      const dt = Math.min(0.05, (now - prev) / 1000)
      prev = now
      if (!this.F.length || !this.W) this.setup()
      this.hover += (this.hoverT - this.hover) * (1 - Math.exp(-dt / 0.25))
      this.ph += dt * (0.7 + 0.5 * this.hover)
      this.wx += dt * (0.6 + 1.2 * this.hover)
      const r = Math.min(1, t / 0.8)
      this.revealK = 1 - Math.pow(1 - r, 3)
      if (this.F.length) this.frame(t)
      this.raf = requestAnimationFrame(tick)
    }
    this.raf = requestAnimationFrame(tick)
  }

  stop(): void {
    cancelAnimationFrame(this.raf)
    this.ro?.disconnect()
    this.ro = undefined
  }
}
