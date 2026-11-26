/**
 * Wahlen 2027 – Auszählungsstand Nationalrat (Videowand)
 * OGraf-Grafik nach EBU OGraf v1 (https://ograf.ebu.io/v1/specification/docs/Specification.html)
 *
 * Vollbild für die Studio-Videowand, Referenz SRF Wahlen 2023:
 *   Auszählungsstand Nationalrat [+]
 *   ■ 1  Resultat          Schweizer Karte mit Kantonsgrenzen:
 *   ■ 2  Hochrechnung        dunkelrot = Resultat, rosa = Hochrechnung, grau = kein Resultat
 *   ■ 23 Kein Resultat
 *
 * Geometrie: swisstopo/BFS generalisierte Grenzen (npm «swiss-maps», Jahr 2026), in karte.mjs als SVG-Pfade.
 * Schritte (stepCount 1): playAction blendet ein, ein weiterer playAction oder stopAction blendet aus.
 * updateAction: Kantone wechseln ihre Farbe, Zähler in der Legende aktualisieren sich.
 */
import KARTE from './karte.mjs'

const W = 1920
const H = 1080

const L = {
  rand: 150, titelTop: 86, titelSize: 80, flagge: 66,
  legendeX: 150, legendeY: 330, kasten: 56, zeilenAbstand: 78, legendeSize: 36, zahlSize: 36,
  kartenX: 730, kartenY: 322, kartenBreite: 1010
}

const FARBE = {
  hintergrund: '#e1ebea', text: '#1d1d1b', flagge: '#d52b1e',
  resultat: '#9b0a3c', hochrechnung: '#ec5774', keines: '#595b5d',
  grenze: '#eef3f2', see: '#eef5f6'
}

const STATUS = ['resultat', 'hochrechnung', 'keines']

const DEFAULTS = Object.freeze({
  titel: 'Auszählungsstand Nationalrat',
  flagge: true,
  legende_resultat: 'Resultat',
  legende_hochrechnung: 'Hochrechnung',
  legende_keines: 'Kein Resultat',
  kantone: []
})

const FONT_FAMILY = 'Wahlen Text'
const FONT_FALLBACK = '"SRG SSR Type Text", "SRG SSR Type", "Helvetica Neue", Arial, sans-serif'

const CSS = `
  :host { display: block; position: relative; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .stage { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; transform-origin: 0 0; overflow: hidden;
           background: ${FARBE.hintergrund}; color: ${FARBE.text}; opacity: 0;
           font-family: "${FONT_FAMILY}", ${FONT_FALLBACK}; -webkit-font-smoothing: antialiased; }
  .titel { position: absolute; left: ${L.rand}px; top: ${L.titelTop}px; display: flex; align-items: center; gap: 26px;
           font-size: ${L.titelSize}px; line-height: 1.15; white-space: nowrap; }
  .titel svg { width: ${L.flagge}px; height: ${L.flagge}px; flex: none; margin-top: -6px; }
  .titel svg[hidden] { display: none; }
  .legende { position: absolute; left: ${L.legendeX}px; top: ${L.legendeY}px; }
  .zeile { display: flex; align-items: center; gap: 22px; height: ${L.kasten}px; margin-bottom: ${L.zeilenAbstand - L.kasten}px;
           font-size: ${L.legendeSize}px; white-space: nowrap; }
  .kasten { width: ${L.kasten}px; height: ${L.kasten}px; display: flex; align-items: center; justify-content: center;
            color: #fff; font-size: ${L.zahlSize}px; font-weight: 700; font-variant-numeric: tabular-nums; }
  svg.karte { position: absolute; left: ${L.kartenX}px; top: ${L.kartenY}px; width: ${L.kartenBreite}px; overflow: visible; }
  svg.karte path.kt { stroke: ${FARBE.grenze}; stroke-width: 1.6; stroke-linejoin: round; }
  svg.karte path.see { fill: ${FARBE.see}; stroke: none; }
`

class Auszaehlungsstand extends HTMLElement {
  constructor () {
    super()
    this._data = { ...DEFAULTS }
    this._sichtbar = false
    this._laufend = new Set()
    this._warteschlange = Promise.resolve()
    this._resizeObserver = null
  }

  async load (params) {
    this._data = this._normalisieren({ ...DEFAULTS, ...(params?.data || {}) })
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' })
    const [x0, y0, x1, y1] = KARTE.bounds
    const kantone = Object.entries(KARTE.kantone).map(([k, d]) => `<path class="kt" data-kt="${k}" d="${d}" fill="${FARBE.keines}"/>`).join('')
    const seen = KARTE.seen.map(d => `<path class="see" d="${d}"/>`).join('')
    const zeilen = STATUS.map(s => `<div class="zeile" data-s="${s}"><div class="kasten" style="background:${FARBE[s]}"></div><span class="txt"></span></div>`).join('')
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="stage">
        <div class="titel"><span class="t"></span>
          <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" fill="${FARBE.flagge}"/>
            <path fill="#fff" d="M13 6h6v7h7v6h-7v7h-6v-7H6v-6h7z"/></svg></div>
        <div class="legende">${zeilen}</div>
        <svg class="karte" viewBox="${x0 - 2} ${y0 - 2} ${x1 - x0 + 4} ${y1 - y0 + 4}">${kantone}${seen}</svg>
      </div>`
    const q = s => this.shadowRoot.querySelector(s)
    this._stage = q('.stage')
    this._pfade = Object.fromEntries([...this.shadowRoot.querySelectorAll('path.kt')].map(p => [p.dataset.kt, p]))
    this._wertSetzen(true)
    this._skalieren()
    this._resizeObserver = new ResizeObserver(() => this._skalieren())
    this._resizeObserver.observe(this)
    await this._schriftenLaden()
    return { statusCode: 200, statusMessage: 'Geladen' }
  }

  async dispose () {
    this._alleAnimationenBeenden()
    if (this._resizeObserver) this._resizeObserver.disconnect()
    if (this.shadowRoot) this.shadowRoot.innerHTML = ''
    return { statusCode: 200, statusMessage: 'Entladen' }
  }

  playAction (params = {}) {
    return this._einreihen(async () => {
      const skip = !!params.skipAnimation
      const ziel = (Number.isInteger(params.goto) && params.goto >= 0) ? params.goto : (this._sichtbar ? 1 : 0)
      if (ziel >= 1) {
        await this._aus(skip)
        return { statusCode: 200, statusMessage: 'Ausgeblendet', currentStep: undefined }
      }
      if (!this._sichtbar) await this._ein(skip)
      return { statusCode: 200, statusMessage: 'OK', currentStep: 0 }
    })
  }

  stopAction (params = {}) {
    return this._einreihen(async () => {
      await this._aus(!!params.skipAnimation)
      return { statusCode: 200, statusMessage: 'Ausgeblendet' }
    })
  }

  updateAction (params = {}) {
    return this._einreihen(async () => {
      this._data = this._normalisieren({ ...this._data, ...(params.data || {}) })
      this._textSetzen()
      await this._farbenSetzen(this._sichtbar && !params.skipAnimation)
      return { statusCode: 200, statusMessage: 'Aktualisiert' }
    })
  }

  customAction (params = {}) {
    return Promise.resolve({ statusCode: 400, statusMessage: `Unbekannte customAction: ${params.id}` })
  }

  // ---------------- Daten ----------------

  _normalisieren (d) {
    const n = { ...d }
    n.flagge = n.flagge !== false
    n.kantone = Array.isArray(n.kantone) ? n.kantone.filter(k => k && KARTE.kantone[k.kanton]) : []
    return n
  }

  _status (kuerzel) {
    const k = this._data.kantone.find(x => x.kanton === kuerzel)
    return k && FARBE[k.status] && k.status !== 'keines' ? k.status : 'keines'
  }

  _zaehler () {
    const z = { resultat: 0, hochrechnung: 0, keines: 0 }
    for (const k of Object.keys(KARTE.kantone)) z[this._status(k)]++
    return z
  }

  _skalieren () {
    if (!this._stage) return
    const r = this.getBoundingClientRect()
    const w = r.width || W
    const h = r.height || H
    const s = Math.min(w / W, h / H)
    this._stage.style.transform = `translate(${(w - W * s) / 2}px, ${(h - H * s) / 2}px) scale(${s})`
  }

  async _schriftenLaden () {
    try {
      const basis = new URL('./fonts/', import.meta.url)
      const r = await fetch(new URL('fonts.json', basis))
      if (!r.ok) return
      const liste = await r.json()
      await Promise.all((liste.schriften || []).map(async f => {
        try {
          const face = new FontFace(FONT_FAMILY, `url("${new URL(f.datei, basis)}")`, { weight: String(f.gewicht || 400), style: f.stil || 'normal' })
          await Promise.race([face.load(), new Promise((_, rej) => setTimeout(() => rej(new Error('Zeit')), 3000))])
          document.fonts.add(face)
        } catch (e) { /* Rückfallschrift */ }
      }))
    } catch (e) { /* keine fonts.json */ }
  }

  _textSetzen () {
    const sr = this.shadowRoot
    if (!sr) return
    sr.querySelector('.titel .t').textContent = this._data.titel || ''
    sr.querySelector('.titel svg').toggleAttribute('hidden', !this._data.flagge)
    const z = this._zaehler()
    for (const s of STATUS) {
      const zeile = sr.querySelector(`.zeile[data-s="${s}"]`)
      zeile.querySelector('.kasten').textContent = String(z[s])
      zeile.querySelector('.txt').textContent = this._data[`legende_${s}`] || ''
    }
  }

  _wertSetzen () {
    this._textSetzen()
    for (const [k, p] of Object.entries(this._pfade)) p.style.fill = FARBE[this._status(k)]
  }

  // ---------------- Animationen ----------------

  _anim (el, keyframes, optionen, skip) {
    const a = el.animate(keyframes, { fill: 'forwards', ...optionen, ...(skip ? { duration: 0, delay: 0 } : {}) })
    this._laufend.add(a)
    return a.finished.then(() => {
      try { a.commitStyles() } catch (e) { /* nicht mehr im DOM */ }
      a.cancel()
    }).catch(() => {}).finally(() => this._laufend.delete(a))
  }

  _alleAnimationenBeenden () {
    for (const a of [...this._laufend]) { try { a.finish() } catch (e) { /* schon fertig */ } }
  }

  _einreihen (fn) {
    const p = this._warteschlange.then(fn, fn)
    this._warteschlange = p.catch(() => {})
    return p.catch(e => ({ statusCode: 500, statusMessage: String(e && e.message ? e.message : e) }))
  }

  async _farbenSetzen (animiert) {
    const jobs = []
    for (const [k, p] of Object.entries(this._pfade)) {
      const ziel = FARBE[this._status(k)]
      const ist = p.style.fill
      if (!animiert) { p.style.fill = ziel; continue }
      jobs.push(this._anim(p, [{ fill: ist }, { fill: ziel }], { duration: 450, easing: 'ease-in-out' }, false))
      p.style.fill = ziel
    }
    await Promise.all(jobs)
  }

  async _ein (skip) {
    this._wertSetzen()
    const karte = this.shadowRoot.querySelector('svg.karte')
    const legende = this.shadowRoot.querySelector('.legende')
    karte.style.opacity = '0'
    legende.style.opacity = '0'
    this._stage.style.opacity = '1'
    this._sichtbar = true
    if (!skip) await this._anim(this._stage, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, easing: 'linear' }, false)
    await Promise.all([
      this._anim(karte, [{ opacity: 0 }, { opacity: 1 }], { duration: 350, delay: 250, easing: 'linear' }, skip),
      this._anim(legende, [{ opacity: 0 }, { opacity: 1 }], { duration: 300, delay: 450, easing: 'linear' }, skip)
    ])
  }

  async _aus (skip) {
    if (!this._sichtbar) return
    await this._anim(this._stage, [{ opacity: 1 }, { opacity: 0 }], { duration: 250, easing: 'linear' }, skip)
    this._stage.style.opacity = '0'
    this._sichtbar = false
  }
}

export default Auszaehlungsstand
