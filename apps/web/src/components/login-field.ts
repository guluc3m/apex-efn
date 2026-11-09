/**
 * Campo de puntos hexagonal del acceso (LoginRD) en WebGL2. Determinista: semilla fija.
 *
 * La CPU solo prepara datos estáticos al (re)dimensionar: tabla de ruido, máscara del árbol y el
 * muestreo del sprite. Cada fotograma es un único draw instanciado (una instancia por celda) cuyo
 * vertex shader calcula campo, intercambio con vecinos, paleta y morph; solo cambian uniformes.
 */
const L = 40
const CELL = 9
const RH = (CELL * Math.sqrt(3)) / 2
const MAX_DPR = 2

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

const VERT = `#version 300 es
precision highp float;
precision highp int;
precision highp sampler2D;
#define CELL ${CELL.toFixed(1)}
#define RH ${RH.toFixed(9)}
#define L ${L.toFixed(1)}
uniform sampler2D uG;    // tabla de ruido 256x256
uniform sampler2D uCell; // RG32F: sombra del árbol (T), retardo del morph (D)
uniform sampler2D uSpr;  // RGBA8: color del sprite + alfa
uniform int uCols, uRows;
uniform vec2 uView, uOrg;
uniform float uTime, uPh, uWx, uSway, uSwapP, uMt, uRev;
out vec2 vP;
out vec3 vCol;
out float vRad;

const float SP[7] = float[7](0.0, 0.2, 0.4, 0.6, 0.78, 0.92, 1.0);
#define C(r, g, b) (vec3(r, g, b) / 255.0)
const vec3 SC[7] = vec3[7](
  C(20.0, 32.0, 22.0), C(38.0, 58.0, 40.0), C(66.0, 94.0, 66.0), C(104.0, 140.0, 102.0),
  C(143.0, 187.0, 139.0), C(160.0, 201.0, 156.0), C(214.0, 232.0, 212.0));

float ih(uint a, uint b) {
  uint h = a * 374761393u + b * 668265263u;
  h = (h ^ (h >> 13)) * 1274126177u;
  return float(h ^ (h >> 16)) / 4294967296.0;
}
float ss(float a, float b, float x) {
  float t = clamp((x - a) / (b - a), 0.0, 1.0);
  return t * t * (3.0 - 2.0 * t);
}
float gv(int x, int y) { return texelFetch(uG, ivec2(x & 255, y & 255), 0).r; }
float noise(vec2 p) {
  vec2 f = floor(p);
  vec2 fr = p - f;
  vec2 w = fr * fr * (3.0 - 2.0 * fr);
  int xi = int(f.x);
  int yi = int(f.y);
  float a = gv(xi, yi), b = gv(xi + 1, yi), c = gv(xi, yi + 1), d = gv(xi + 1, yi + 1);
  return a + (b - a) * w.x + (c - a) * w.y + (a - b - c + d) * w.x * w.y;
}
vec3 pal(float s) {
  int j = 0;
  for (int k = 0; k < 5; k++) if (s > SP[j + 1]) j++;
  return mix(SC[j], SC[j + 1], (s - SP[j]) / (SP[j + 1] - SP[j]));
}
// (valor 0..1 del color, intensidad de tinte frío) de la celda (c, r)
vec2 field(int c, int r) {
  float cx = (float(c) + 0.5 + 0.5 * float(r & 1)) * CELL + uOrg.x;
  float cy = (float(r) + 0.5) * RH + uOrg.y;
  float amp = uSway * (0.2 + 0.8 * (1.0 - float(r) / float(uRows)));
  float sw = sin(uTime * 0.7 + float(r) * 0.03) * amp + sin(uTime * 1.9 + float(r) * 0.09) * amp * 0.25;
  vec2 np = vec2((cx + uWx * 26.0) / (CELL * 30.0), cy / (CELL * 2.8));
  float n = 0.58 * noise(np) + 0.28 * noise(np * vec2(2.1, 2.2) + vec2(5.3, 1.7)) + 0.14 * noise(np * vec2(4.4, 4.1) + vec2(9.1, 3.3));
  float lo = noise(vec2(cx / (uView.x * 0.45) + uWx * 0.02, cy / (uView.y * 0.28) + 7.7));
  float s = 0.66 + 0.62 * (n - 0.5) - 0.25 * ss(0.52, 0.8, lo);
  float fc = clamp(float(c) + sw, 0.0, float(uCols) - 1.001);
  int c0 = int(floor(fc));
  float fr = fc - float(c0);
  float tk = texelFetch(uCell, ivec2(c0, r), 0).r * (1.0 - fr) + texelFetch(uCell, ivec2(c0 + 1, r), 0).r * fr;
  s = s * (1.0 - 0.5 * tk) - 0.03 * tk * n;
  s *= 1.0 - 0.12 * (cy / uView.y) * (cy / uView.y);
  if (n > 0.8) s += (n - 0.8) * 1.5 * (1.0 - tk);
  float sh = clamp((1.0 - cy / (uView.y * 0.75)) * (0.55 + 0.9 * lo) * (1.0 - 0.8 * tk), 0.0, 1.0);
  return vec2(s, sh);
}

void hide() { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); }

void main() {
  int id = gl_InstanceID;
  int r = id / uCols;
  int c = id - r * uCols;
  uint i = uint(id);
  float cx = (float(c) + 0.5 + 0.5 * float(r & 1)) * CELL + uOrg.x;
  float cy = (float(r) + 0.5) * RH + uOrg.y;
  if (cy > uView.y + CELL || cy > uRev * (uView.y + CELL)) { hide(); return; }

  // Intercambio de color con un vecino (izquierda/derecha/arriba) para mantener las estrías.
  vec2 fs = field(c, r);
  float u = uPh + ih(i, 77u) * 17.0;
  float q = floor(u);
  float fq = u - q;
  uint qu = uint(q);
  float v = fs.x;
  if (ih(i, qu) < uSwapP) {
    int k = min(5, int(floor(ih(i, qu + 4099u) * 8.0)));
    int j = k < 4 ? (k & 1) : k - 2;
    int o = r & 1;
    int nc = j == 0 ? c - 1 : j == 1 ? c + 1 : j == 2 ? c - 1 + o : c + o;
    int nr = j < 2 ? r : r - 1;
    nc = (nc + uCols) % uCols;
    nr = (nr + uRows) % uRows;
    float m = ss(0.0, 0.15, fq) * (1.0 - ss(0.85, 1.0, fq));
    v += (field(nc, nr).x - v) * m;
  }
  v += (ih(i, qu + 7u) + (ih(i, qu + 8u) - ih(i, qu + 7u)) * ss(0.0, 1.0, fq) - 0.5) * 0.12;

  float s = floor(clamp(v, 0.0, 1.0) * (L - 1.0) + 0.5) / (L - 1.0);
  float tint = floor(fs.y * 3.0 + 0.5) / 3.0 * 0.8;
  vec3 cool = vec3(14.0 + 150.0 * pow(s, 1.2), 30.0 + 170.0 * s, 26.0 + 148.0 * s) / 255.0;
  vec3 col = mix(pal(s), cool, tint);

  // Morph hacia el sprite: color y radio interpolados, con un pequeño desvío orbital.
  vec4 sp = texelFetch(uSpr, ivec2(c, r), 0);
  float loc = ss(0.0, 1.0, (uMt - texelFetch(uCell, ivec2(c, r), 0).g) / 0.38);
  float target = sp.a > 0.1 ? 0.47 * min(1.0, sp.a * 1.5) : 0.0;
  float rad = CELL * (0.3 + (target - 0.3) * loc);
  if (rad < 0.4) { hide(); return; }
  float ang = ih(i, 5u) * 6.2832;
  float off = sin(3.14159265 * min(1.0, loc)) * CELL * 2.5 * ih(i, 6u);
  vec2 ctr = vec2(cx, cy) + vec2(cos(ang), sin(ang)) * off;

  vec2 corner = vec2(float(gl_VertexID & 1), float(gl_VertexID >> 1)) * 2.0 - 1.0;
  vP = corner * (rad + 1.0);
  vRad = rad;
  vCol = mix(col, sp.rgb, loc);
  gl_Position = vec4((ctr + vP) / uView * vec2(2.0, -2.0) + vec2(-1.0, 1.0), 0.0, 1.0);
}
`

const FRAG = `#version 300 es
precision mediump float;
in vec2 vP;
in vec3 vCol;
in float vRad;
out vec4 o;
void main() {
  float a = clamp(vRad + 0.5 - length(vP), 0.0, 1.0);
  o = vec4(vCol * a, a);
}
`

export class LoginField {
  hoverT = 0
  private hover = 0
  private ph = 0
  private wx = 0
  private raf = 0
  private resizeTimer: ReturnType<typeof setTimeout> | undefined
  private ro: ResizeObserver | undefined
  private revealK = 1
  private W = 0
  private H = 0
  private cols = 0
  private rows = 0
  private G = new Float32Array(0)
  private T = new Float32Array(0)
  private CX = new Float32Array(0)
  private CY = new Float32Array(0)
  // Easter egg: los puntos se reorganizan en un sprite (ver `morph`).
  private sprite: HTMLImageElement | undefined
  private morphTo = 0
  private mt = 0
  private reduce = false
  private D = new Float32Array(0)
  private spr = new Uint8Array(0)
  // WebGL
  private gl: WebGL2RenderingContext | null = null
  private prog: WebGLProgram | null = null
  private linked = false
  private tex: WebGLTexture[] = []
  private loc = new Map<string, WebGLUniformLocation | null>()

  constructor(private readonly cv: HTMLCanvasElement) {}

  private onLost = (e: Event): void => e.preventDefault()
  private onRestored = (): void => {
    if (this.initGL()) this.setup()
  }

  private initGL(): boolean {
    const gl = this.cv.getContext('webgl2', {
      antialias: false,
      alpha: true,
      premultipliedAlpha: true,
    })
    if (!gl) return false
    const sh = (type: number, src: string): WebGLShader => {
      const s = gl.createShader(type)!
      gl.shaderSource(s, src)
      gl.compileShader(s)
      return s
    }
    // Se envía a compilar y NO se consulta el estado todavía: el driver compila mientras la CPU
    // prepara el árbol y el sprite; `link()` lo comprueba después.
    const prog = gl.createProgram()
    gl.attachShader(prog, sh(gl.VERTEX_SHADER, VERT))
    gl.attachShader(prog, sh(gl.FRAGMENT_SHADER, FRAG))
    gl.linkProgram(prog)
    gl.pixelStorei(gl.UNPACK_ALIGNMENT, 1)
    gl.bindVertexArray(gl.createVertexArray())
    this.tex = [0, 1, 2].map((k) => {
      const t = gl.createTexture()
      gl.activeTexture(gl.TEXTURE0 + k)
      gl.bindTexture(gl.TEXTURE_2D, t)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE)
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
      return t
    })
    this.gl = gl
    this.prog = prog
    this.loc.clear()
    this.linked = false
    return true
  }

  /** Comprueba la compilación (lanza si falla) y deja listo el estado del programa. Idempotente. */
  private link(): void {
    const { gl, prog } = this
    if (!gl || !prog || this.linked) return
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS))
      throw new Error(gl.getProgramInfoLog(prog) ?? 'link')
    gl.useProgram(prog)
    gl.enable(gl.BLEND)
    gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.clearColor(0, 0, 0, 0)
    gl.uniform1i(this.u('uG'), 0)
    gl.uniform1i(this.u('uCell'), 1)
    gl.uniform1i(this.u('uSpr'), 2)
    this.linked = true
  }

  private u(name: string): WebGLUniformLocation | null {
    let l = this.loc.get(name)
    if (l === undefined && this.gl && this.prog) {
      l = this.gl.getUniformLocation(this.prog, name)
      this.loc.set(name, l)
    }
    return l ?? null
  }

  /** Sube las texturas estáticas: ruido, árbol + retardo de morph, y color del sprite. */
  private upload(): void {
    const { gl, cols, rows, T, D } = this
    if (!gl || !cols || !T.length) return
    const n = cols * rows
    const cell = new Float32Array(n * 2)
    for (let i = 0; i < n; i++) {
      cell[i * 2] = T[i] ?? 0
      cell[i * 2 + 1] = D[i] ?? 0
    }
    gl.activeTexture(gl.TEXTURE0)
    gl.bindTexture(gl.TEXTURE_2D, this.tex[0] ?? null)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.R32F, 256, 256, 0, gl.RED, gl.FLOAT, this.G)
    gl.activeTexture(gl.TEXTURE1)
    gl.bindTexture(gl.TEXTURE_2D, this.tex[1] ?? null)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RG32F, cols, rows, 0, gl.RG, gl.FLOAT, cell)
    gl.activeTexture(gl.TEXTURE2)
    gl.bindTexture(gl.TEXTURE_2D, this.tex[2] ?? null)
    gl.texImage2D(
      gl.TEXTURE_2D,
      0,
      gl.RGBA8,
      cols,
      rows,
      0,
      gl.RGBA,
      gl.UNSIGNED_BYTE,
      this.spr.length ? this.spr : new Uint8Array(n * 4)
    )
  }

  /** Rejilla hexagonal + árbol. */
  private setup(): void {
    const cv = this.cv
    const parent = cv.parentElement
    if (!parent || !this.gl) return
    const box = parent.getBoundingClientRect()
    const dpr = Math.min(window.devicePixelRatio || 1, MAX_DPR)
    this.W = box.width
    this.H = box.height
    cv.width = Math.max(1, Math.round(box.width * dpr))
    cv.height = Math.max(1, Math.round(box.height * dpr))
    this.gl.viewport(0, 0, cv.width, cv.height)
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
    this.T = new Float32Array(n)
    this.CX = new Float32Array(n)
    this.CY = new Float32Array(n)
    const ox = (box.width - cols * CELL) / 2
    const oy = (box.height - rows * RH) / 2
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const k = r * cols + c
        this.CX[k] = (c + 0.5 + 0.5 * (r & 1)) * CELL + ox
        this.CY[k] = (r + 0.5) * RH + oy
      }
    }
    this.buildTree(rnd)
    this.sampleSprite()
    this.link()
    this.upload()
    this.gl.uniform2f(this.u('uView'), this.W, this.H)
    this.gl.uniform2f(this.u('uOrg'), ox, oy)
    this.gl.uniform1i(this.u('uCols'), cols)
    this.gl.uniform1i(this.u('uRows'), rows)
  }

  /** Activa/desactiva la transformación en el sprite (carga la imagen la primera vez). */
  morph(on: boolean): void {
    if (!this.gl) return // sin WebGL2 se usa la imagen estática: no hay morph
    this.morphTo = on ? 1 : 0
    if (on && !this.sprite) {
      const img = new Image()
      img.onload = () => {
        this.sprite = img
        this.sampleSprite()
        this.upload()
        if (this.reduce) this.settle()
      }
      img.src = '/yoshi.png'
    } else if (this.reduce) this.settle()
  }

  private settle(): void {
    this.mt = this.morphTo
    if (this.T.length) this.frame(2)
  }

  /** Muestrea el sprite (con alfa) en el centro de cada celda y fija el retardo de la onda desde el centro. */
  private sampleSprite(): void {
    const img = this.sprite
    const { W, H, CX, CY } = this
    const n = CX.length
    if (!img || !n) return
    const oc = document.createElement('canvas')
    oc.width = Math.max(1, Math.round(W))
    oc.height = Math.max(1, Math.round(H))
    const ctx = oc.getContext('2d', { willReadFrequently: true })
    if (!ctx) return
    // Cabe en la zona libre sobre la tarjeta de ofertas.
    const ph = Math.min(H * 0.56, (W * 0.85 * img.height) / img.width)
    const pw = (ph * img.width) / img.height
    const x0 = (W - pw) / 2
    const y0 = H * 0.05
    ctx.imageSmoothingQuality = 'high'
    ctx.drawImage(img, x0, y0, pw, ph)
    const data = ctx.getImageData(0, 0, oc.width, oc.height).data
    this.D = new Float32Array(n)
    this.spr = new Uint8Array(n * 4)
    const mx = Math.hypot(W / 2, H / 2)
    const cy0 = y0 + ph / 2
    const o = CELL * 0.3
    for (let i = 0; i < n; i++) {
      const x = CX[i] ?? 0
      const y = CY[i] ?? 0
      let r = 0
      let g = 0
      let b = 0
      let a = 0
      for (const [dx, dy] of [
        [0, 0],
        [-o, 0],
        [o, 0],
        [0, -o],
        [0, o],
      ] as const) {
        const px = Math.round(x + dx)
        const py = Math.round(y + dy)
        if (px < 0 || py < 0 || px >= oc.width || py >= oc.height) continue
        const k = (py * oc.width + px) * 4
        const al = (data[k + 3] ?? 0) / 255
        r += (data[k] ?? 0) * al
        g += (data[k + 1] ?? 0) * al
        b += (data[k + 2] ?? 0) * al
        a += al
      }
      this.spr[i * 4] = a ? Math.round(r / a) : 0
      this.spr[i * 4 + 1] = a ? Math.round(g / a) : 0
      this.spr[i * 4 + 2] = a ? Math.round(b / a) : 0
      this.spr[i * 4 + 3] = Math.round((a / 5) * 255)
      // La onda sale del centro del sprite hacia fuera (retardo 0..0.62 del recorrido).
      this.D[i] = 0.5 * clamp01(Math.hypot(x - W / 2, y - cy0) / mx) + 0.12 * ih(i, 31)
    }
  }

  /** Silueta de árbol: tronco, ramas recursivas y copas, en una máscara de oscuridad por celda. */
  private buildTree(rnd: () => number): void {
    const { W, H, CX, CY, T } = this
    const segs: Seg[] = []
    const tips: Tip[] = []
    const grow = (
      x: number,
      y: number,
      ang: number,
      len: number,
      th: number,
      depth: number
    ): void => {
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
        grow(
          x2,
          y2,
          ang + dir * (0.5 + rnd() * 0.5),
          len * (0.62 + rnd() * 0.12),
          th2 * 0.78,
          depth - 1
        )
      }
    }
    grow(W * 0.46, H * 1.06, -0.1, H * 0.22, Math.max(26, W * 0.07), 7)
    // Cada segmento/copa recorre solo las celdas de su caja (alcance = half + blur = 2.1·half + 14),
    // en vez de que cada celda pruebe todos los segmentos. T acumula el máximo.
    const cols = this.cols
    const rows = this.rows
    const ox = (CX[0] ?? 0) - CELL * 0.5
    const oy = (CY[0] ?? 0) - RH * 0.5
    const each = (
      x0: number,
      x1: number,
      y0: number,
      y1: number,
      fn: (i: number, x: number, y: number) => void
    ): void => {
      const r0 = Math.max(0, Math.floor((y0 - oy) / RH - 0.5))
      const r1 = Math.min(rows - 1, Math.ceil((y1 - oy) / RH - 0.5))
      const c0 = Math.max(0, Math.floor((x0 - ox) / CELL - 1))
      const c1 = Math.min(cols - 1, Math.ceil((x1 - ox) / CELL))
      for (let r = r0; r <= r1; r++) {
        for (let c = c0; c <= c1; c++) {
          const i = r * cols + c
          fn(i, CX[i] ?? 0, CY[i] ?? 0)
        }
      }
    }
    for (const g of segs) {
      const reach = Math.max(g[4], g[5]) * 0.5 * 2.1 + 14
      const dx = g[2] - g[0]
      const dy = g[3] - g[1]
      each(
        Math.min(g[0], g[2]) - reach,
        Math.max(g[0], g[2]) + reach,
        Math.min(g[1], g[3]) - reach,
        Math.max(g[1], g[3]) + reach,
        (i, x, y) => {
          const t = Math.max(
            0,
            Math.min(1, ((x - g[0]) * dx + (y - g[1]) * dy) / (dx * dx + dy * dy))
          )
          const d = Math.hypot(x - (g[0] + dx * t), y - (g[1] + dy * t))
          const half = (g[4] + (g[5] - g[4]) * t) * 0.5
          const blur = 14 + half * 1.1
          if (d > half + blur) return
          T[i] = Math.max(T[i] ?? 0, 1 - ss(half * 0.6, half + blur, d))
        }
      )
    }
    for (const g of tips) {
      const rad = g[2] * 1.5
      each(g[0] - rad, g[0] + rad, g[1] - rad, g[1] + rad, (i, x, y) => {
        const d = Math.hypot(x - g[0], y - g[1])
        if (d < rad) T[i] = Math.max(T[i] ?? 0, 0.55 * (1 - ss(0, rad, d)))
      })
    }
  }

  private frame(t: number): void {
    const { gl } = this
    if (!gl || !this.cols || gl.isContextLost()) return
    gl.uniform1f(this.u('uTime'), t)
    gl.uniform1f(this.u('uPh'), this.ph)
    gl.uniform1f(this.u('uWx'), this.wx)
    gl.uniform1f(this.u('uSway'), 2.2 + 1.5 * this.hover)
    gl.uniform1f(this.u('uSwapP'), 0.55 + 0.2 * this.hover)
    // Sin sprite cargado el morph no se ve (retardos a 0 y alfa 0 dejarían el radio base).
    gl.uniform1f(this.u('uMt'), this.sprite ? this.mt : 0)
    gl.uniform1f(this.u('uRev'), this.revealK)
    gl.clear(gl.COLOR_BUFFER_BIT)
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.cols * this.rows)
  }

  private still(): void {
    this.revealK = 1
    this.mt = this.morphTo
    this.ph = 3.3
    this.wx = 1.5
    this.frame(2)
  }

  /** Arranca la animación. Devuelve false si no hay WebGL2 (el llamador pinta la imagen estática). */
  start(): boolean {
    cancelAnimationFrame(this.raf)
    this.cv.addEventListener('webglcontextlost', this.onLost)
    this.cv.addEventListener('webglcontextrestored', this.onRestored)
    let ok = false
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    this.reduce = reduce
    try {
      ok = this.initGL()
      if (ok) this.setup()
    } catch {
      ok = false // el shader no compila en esta GPU/driver
    }
    if (!ok) {
      this.stop()
      return false
    }
    const parent = this.cv.parentElement
    if (typeof ResizeObserver !== 'undefined' && !this.ro && parent) {
      let first = true
      this.ro = new ResizeObserver(() => {
        if (first) {
          first = false
          return
        }
        clearTimeout(this.resizeTimer)
        this.resizeTimer = setTimeout(() => {
          this.setup()
          if (reduce) this.still()
        }, 120)
      })
      this.ro.observe(parent)
    }
    if (reduce) {
      this.still()
      return true
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
      this.hover += (this.hoverT - this.hover) * (1 - Math.exp(-dt / 0.25))
      this.ph += dt * (0.7 + 0.5 * this.hover)
      this.wx += dt * (0.6 + 1.2 * this.hover)
      this.mt = clamp01(this.mt + Math.max(-dt / 2.4, Math.min(dt / 2.4, this.morphTo - this.mt)))
      const r = Math.min(1, t / 0.8)
      this.revealK = 1 - Math.pow(1 - r, 3)
      this.frame(t)
      this.raf = requestAnimationFrame(tick)
    }
    this.raf = requestAnimationFrame(tick)
    return true
  }

  stop(): void {
    cancelAnimationFrame(this.raf)
    clearTimeout(this.resizeTimer)
    this.ro?.disconnect()
    this.ro = undefined
    this.cv.removeEventListener('webglcontextlost', this.onLost)
    this.cv.removeEventListener('webglcontextrestored', this.onRestored)
    if (this.gl) {
      for (const t of this.tex) this.gl.deleteTexture(t)
      this.gl.deleteProgram(this.prog)
    }
    this.gl = null
    this.prog = null
    this.tex = []
  }
}
