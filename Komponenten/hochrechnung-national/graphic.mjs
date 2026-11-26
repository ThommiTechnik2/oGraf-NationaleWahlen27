/**
 * Wahlen 2027 – Hochrechnung National (Videowand)
 * OGraf-Grafik nach EBU OGraf v1 (https://ograf.ebu.io/v1/specification/docs/Specification.html)
 *
 * Vollbild-Grafik für die Videowand im Studio (deckender Hintergrund), Referenz SRF Wahlen 2023:
 *   Hochrechnung Nationalrat [+]
 *     SVP     SP     FDP    Mitte   Grüne   GLP        <- Name
 *    29.0%  17.2%  14.6%  14.7%    9.1%   7.1%         <- Wähleranteil (fett, auf heller Fläche)
 *    +3.4%  ±0.4%  -0.5%  +0.9%   -4.1%  -0.7%         <- Veränderung (± = im Fehlerbereich)
 *     ██
 *     ██     ██     ██     ██
 *     ██     ██     ██     ██      ██     ██
 *   ─────────────────────────────────────────          <- Grundlinie
 *
 * Schritte (stepCount -1): ein Schritt pro Partei. Jeder Schritt lässt den nächsten Balken wachsen,
 * die neueste Partei ist hervorgehoben (grössere Schrift). Ist eine Seite voll (Standard 6 Parteien),
 * leert der nächste Schritt die Fläche und beginnt die nächste Seite. Über den letzten Schritt hinaus: aus.
 * Alle Balken haben denselben Massstab (grösste Partei), kleine Parteien bleiben also klein – wie im Original.
 *
 * Animationen (aus der Referenz gemessen): Balken wächst 420 ms, Beschriftung blendet nach 180 ms in 250 ms ein;
 * Seitenwechsel: harter Schnitt auf leere Fläche, nach 300 ms wächst der erste Balken der neuen Seite.
 */

const W = 1920
const H = 1080

const L = {
  rand: 150,            // linker Rand Titel
  titelTop: 86,
  titelSize: 80,
  flagge: 66,
  spalte0: 268,         // Mitte der ersten Spalte
  spaltenAbstand: 258,
  balkenBreite: 132,
  labelTop: 238,        // Oberkante Beschriftung
  nameSize: 32,
  wertSize: 42,
  diffSize: 32,
  grundlinie: 905,      // y der Grundlinie
  balkenMax: 490,       // Höhe des höchsten Balkens
  linieVon: 176,
  linieBis: 1650,
  aktivSkala: 1.28      // Hervorhebung der neuesten Partei
}

const FARBE = {
  hintergrund: '#e1ebea',
  text: '#1d1d1b',
  leise: '#3a3d3c',
  wertFlaeche: '#f2f6f5',
  linie: '#7c8786',
  flagge: '#d52b1e'
}

const DEFAULTS = Object.freeze({
  titel: 'Hochrechnung Nationalrat',
  flagge: true,
  nachkommastellen: 1,
  pro_seite: 6,
  seiten: [],
  parteien: []
})

const FONT_FAMILY = 'Wahlen Text'
const FONT_FALLBACK = '"SRG SSR Type Text", "SRG SSR Type", "Helvetica Neue", Arial, sans-serif'
const EASE_BALKEN = 'cubic-bezier(0.22, 0.8, 0.25, 1)'

const CSS = `
  :host { display: block; position: relative; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .stage { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; transform-origin: 0 0; overflow: hidden;
           background: ${FARBE.hintergrund}; color: ${FARBE.text}; opacity: 0;
           font-family: "${FONT_FAMILY}", ${FONT_FALLBACK}; -webkit-font-smoothing: antialiased; }
  .titel { position: absolute; left: ${L.rand}px; top: ${L.titelTop}px; display: flex; align-items: center; gap: 26px;
           font-size: ${L.titelSize}px; line-height: 1.15; font-weight: 400; white-space: nowrap; }
  .titel svg { width: ${L.flagge}px; height: ${L.flagge}px; flex: none; margin-top: -6px; }
  .titel svg[hidden] { display: none; }
  .linie { position: absolute; left: ${L.linieVon}px; top: ${L.grundlinie}px; width: ${L.linieBis - L.linieVon}px; height: 3px;
           background: ${FARBE.linie}; }
  .spalte { position: absolute; top: 0; width: 0; height: ${H}px; }
  .label { position: absolute; left: -120px; width: 240px; top: ${L.labelTop}px; text-align: center;
           transform-origin: 50% 100%; white-space: nowrap; }
  .name { font-size: ${L.nameSize}px; line-height: 44px; color: ${FARBE.leise}; }
  .wert { display: inline-block; font-size: ${L.wertSize}px; line-height: 54px; font-weight: 600; padding: 0 10px;
          background: ${FARBE.wertFlaeche}; font-variant-numeric: tabular-nums; }
  .diff { font-size: ${L.diffSize}px; line-height: 46px; color: ${FARBE.leise}; font-variant-numeric: tabular-nums; }
  .balken { position: absolute; left: ${-L.balkenBreite / 2}px; width: ${L.balkenBreite}px; bottom: ${H - L.grundlinie}px;
            height: 0; transform-origin: 50% 100%; }
`

function istZahl (v) { return typeof v === 'number' && Number.isFinite(v) }

function formatWert (v, stellen) { return istZahl(v) ? `${v.toFixed(stellen)}%` : '–' }

function formatDiff (v, stellen, unsicher) {
  if (!istZahl(v)) return ''
  const g = Number(v.toFixed(stellen))
  if (g === 0 || unsicher) return `±${Math.abs(g).toFixed(stellen)}%`
  return `${g > 0 ? '+' : '-'}${Math.abs(g).toFixed(stellen)}%`
}

class HochrechnungNational extends HTMLElement {
  constructor () {
    super()
    this._data = { ...DEFAULTS }
    this._step = undefined
    this._sichtbar = false
    this._seite = -1
    this._spalten = []          // DOM der sichtbaren Spalten der aktuellen Seite
    this._laufend = new Set()
    this._warteschlange = Promise.resolve()
    this._resizeObserver = null
  }

  // ---------------- OGraf ----------------

  async load (params) {
    this._data = this._normalisieren({ ...DEFAULTS, ...(params?.data || {}) })
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' })
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="stage">
        <div class="titel"><span class="t"></span>
          <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" fill="${FARBE.flagge}"/>
            <path fill="#fff" d="M13 6h6v7h7v6h-7v7h-6v-7H6v-6h7z"/></svg></div>
        <div class="flaeche"></div>
        <div class="linie"></div>
      </div>`
    this._stage = this.shadowRoot.querySelector('.stage')
    this._flaeche = this.shadowRoot.querySelector('.flaeche')
    this._titelSetzen()
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
      const n = this._data.parteien.length
      let ziel = (Number.isInteger(params.goto) && params.goto >= 0)
        ? params.goto
        : (this._step ?? -1) + (Number.isInteger(params.delta) ? params.delta : 1)
      if (ziel < 0) ziel = 0
      if (n === 0 || ziel >= n) {
        await this._aus(skip)
        return { statusCode: 200, statusMessage: 'Ende erreicht, ausgeblendet', currentStep: undefined }
      }
      await this._zeigeSchritt(ziel, skip)
      return { statusCode: 200, statusMessage: 'OK', currentStep: ziel }
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
      const alt = this._data
      this._data = this._normalisieren({ ...this._data, ...(params.data || {}) })
      this._titelSetzen()
      if (this._sichtbar && this._step !== undefined) {
        const step = Math.min(this._step, this._data.parteien.length - 1)
        if (step < 0) { await this._aus(!!params.skipAnimation); return { statusCode: 200, statusMessage: 'Leer, ausgeblendet' } }
        const gleicheSeite = this._schluessel(alt, this._seite) === this._schluessel(this._data, this._seiteVon(step))
        if (gleicheSeite) {
          this._step = step
          await this._werteNachfuehren(!!params.skipAnimation)
        } else {
          this._seite = -1
          await this._zeigeSchritt(step, true)
        }
      }
      return { statusCode: 200, statusMessage: 'Aktualisiert' }
    })
  }

  customAction (params = {}) {
    return Promise.resolve({ statusCode: 400, statusMessage: `Unbekannte customAction: ${params.id}` })
  }

  // ---------------- Daten und Seiten ----------------

  _normalisieren (d) {
    const n = { ...d }
    n.pro_seite = Math.max(1, Math.min(6, parseInt(n.pro_seite, 10) || 6))
    n.nachkommastellen = d.nachkommastellen === undefined ? 1 : Math.max(0, Math.min(1, parseInt(n.nachkommastellen, 10) || 0))
    n.flagge = n.flagge !== false
    n.parteien = Array.isArray(n.parteien) ? n.parteien.filter(p => p && p.kurz) : []
    n.seiten = Array.isArray(n.seiten) ? n.seiten.map(x => parseInt(x, 10)).filter(x => x >= 1 && x <= 6) : []
    return n
  }

  _grenzen (data = this._data) {
    const g = []
    let i = 0
    for (const n of data.seiten) {
      if (i >= data.parteien.length) break
      g.push([i, Math.min(i + n, data.parteien.length)])
      i += n
    }
    while (i < data.parteien.length) {
      g.push([i, Math.min(i + data.pro_seite, data.parteien.length)])
      i += data.pro_seite
    }
    return g
  }

  _seiteVon (step, data = this._data) {
    return this._grenzen(data).findIndex(([a, b]) => step >= a && step < b)
  }

  _schluessel (data, seite) {
    const g = this._grenzen(data)[seite]
    return g ? data.parteien.slice(g[0], g[1]).map(p => p.kurz).join(',') : ''
  }

  _skala () {
    const max = Math.max(0, ...this._data.parteien.map(p => istZahl(p.staerke) ? p.staerke : 0))
    return max > 0 ? max : 1
  }

  _balkenHoehe (p) {
    return istZahl(p.staerke) ? Math.max(2, Math.round(p.staerke / this._skala() * L.balkenMax)) : 0
  }

  // ---------------- Aufbau ----------------

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

  _titelSetzen () {
    if (!this.shadowRoot) return
    this.shadowRoot.querySelector('.titel .t').textContent = this._data.titel || ''
    this.shadowRoot.querySelector('.titel svg').toggleAttribute('hidden', !this._data.flagge)
  }

  _spalteErstellen (p, index) {
    const s = document.createElement('div')
    s.className = 'spalte'
    s.style.left = `${L.spalte0 + index * L.spaltenAbstand}px`
    s.innerHTML = '<div class="label"><div class="name"></div><div class="wert"></div><div class="diff"></div></div><div class="balken"></div>'
    this._spalteFuellen(s, p)
    this._flaeche.appendChild(s)
    return s
  }

  _spalteFuellen (s, p) {
    const st = this._data.nachkommastellen
    s.querySelector('.name').textContent = p.kurz
    s.querySelector('.wert').textContent = formatWert(p.staerke, st)
    s.querySelector('.diff').textContent = formatDiff(p.staerke_diff, st, p.staerke_diff_unsicher)
    s.querySelector('.balken').style.background = p.farbe || '#8a8a8a'
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

  _aktivSetzen (index, skip) {
    const laeufe = []
    this._spalten.forEach((s, i) => {
      const label = s.querySelector('.label')
      const soll = i === index ? L.aktivSkala : 1
      const ist = parseFloat(label.dataset.skala || '1')
      if (ist !== soll) {
        label.dataset.skala = String(soll)
        laeufe.push(this._anim(label, [{ transform: `scale(${ist})` }, { transform: `scale(${soll})` }],
          { duration: 250, easing: 'ease-out' }, skip))
      }
    })
    return laeufe
  }

  async _zeigeSchritt (ziel, skip) {
    const seite = this._seiteVon(ziel)
    const [start] = this._grenzen()[seite]
    const anzahl = ziel - start + 1          // Spalten, die danach sichtbar sind

    if (!this._sichtbar) {
      this._stage.style.opacity = '1'
      this._sichtbar = true
      if (!skip) {
        await this._anim(this._stage, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, easing: 'linear' }, false)
        await new Promise(r => setTimeout(r, 250))   // leere Fläche kurz stehen lassen, dann wächst der erste Balken
      }
    }

    if (seite !== this._seite) {
      // Neue Seite: harter Schnitt auf leere Fläche, früheren Spalten dieser Seite sofort, letzte wächst
      this._flaeche.innerHTML = ''
      this._spalten = []
      this._seite = seite
      for (let i = 0; i < anzahl - 1; i++) {
        const s = this._spalteErstellen(this._data.parteien[start + i], i)
        s.querySelector('.balken').style.height = `${this._balkenHoehe(this._data.parteien[start + i])}px`
        this._spalten.push(s)
      }
      if (!skip && this._step !== undefined) await new Promise(r => setTimeout(r, 300))
    }

    // Spalten zurücknehmen (ZURÜCK)
    const laeufe = []
    while (this._spalten.length > anzahl) {
      const s = this._spalten.pop()
      laeufe.push(Promise.all([
        this._anim(s.querySelector('.balken'), [{ transform: 'scaleY(1)' }, { transform: 'scaleY(0)' }], { duration: 250, easing: 'ease-in' }, skip),
        this._anim(s.querySelector('.label'), [{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'linear' }, skip)
      ]).then(() => s.remove()))
    }
    // Neue Spalten wachsen
    while (this._spalten.length < anzahl) {
      const i = this._spalten.length
      const p = this._data.parteien[start + i]
      const s = this._spalteErstellen(p, i)
      const balken = s.querySelector('.balken')
      const label = s.querySelector('.label')
      balken.style.height = `${this._balkenHoehe(p)}px`
      balken.style.transform = 'scaleY(0)'
      label.style.opacity = '0'
      label.dataset.skala = String(L.aktivSkala)
      label.style.transform = `scale(${L.aktivSkala})`
      this._spalten.push(s)
      laeufe.push(this._anim(balken, [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }], { duration: 420, easing: EASE_BALKEN }, skip))
      laeufe.push(this._anim(label, [{ opacity: 0 }, { opacity: 1 }], { duration: 250, delay: 180, easing: 'linear' }, skip))
    }
    laeufe.push(...this._aktivSetzen(anzahl - 1, skip))
    this._step = ziel
    await Promise.all(laeufe)
  }

  async _werteNachfuehren (skip) {
    const [start] = this._grenzen()[this._seite]
    const laeufe = this._spalten.map((s, i) => {
      const p = this._data.parteien[start + i]
      this._spalteFuellen(s, p)
      const balken = s.querySelector('.balken')
      const alt = parseFloat(balken.style.height) || 0
      const neu = this._balkenHoehe(p)
      return this._anim(balken, [{ height: `${alt}px` }, { height: `${neu}px` }], { duration: 400, easing: EASE_BALKEN }, skip)
    })
    await Promise.all(laeufe)
  }

  async _aus (skip) {
    if (!this._sichtbar) { this._step = undefined; return }
    await this._anim(this._stage, [{ opacity: 1 }, { opacity: 0 }], { duration: 250, easing: 'linear' }, skip)
    this._stage.style.opacity = '0'
    this._flaeche.innerHTML = ''
    this._spalten = []
    this._seite = -1
    this._sichtbar = false
    this._step = undefined
  }
}

export default HochrechnungNational
