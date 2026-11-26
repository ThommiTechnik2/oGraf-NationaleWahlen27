/**
 * Wahlen 2027 – Wahlbeteiligung (Videowand)
 * OGraf-Grafik nach EBU OGraf v1 (https://ograf.ebu.io/v1/specification/docs/Specification.html)
 *
 * Vollbild für die Studio-Videowand, Referenz SRF Wahlen 2023:
 *   Wahlbeteiligung [+]
 *        ◔  Ring: Beteiligung in SRF-Rot ab 12 Uhr im Uhrzeigersinn, Rest grau, Wert weiss im roten Teil
 *
 * Schritte (stepCount 1): playAction zeigt die Grafik, ein weiterer playAction oder stopAction blendet aus.
 * updateAction (neuer Wert) lässt den Ring auf den neuen Wert laufen.
 *
 * Animation (aus der Referenz gemessen): Fläche erscheint, nach 400 ms läuft der rote Teil von 12 Uhr
 * im Uhrzeigersinn (800 ms), der Wert blendet ein, danach schliesst der graue Rest den Ring (450 ms).
 */

const W = 1920
const H = 1080

const L = {
  rand: 150, titelTop: 86, titelSize: 80, flagge: 66,
  mitteX: 600, mitteY: 612, aussen: 322, innen: 180,
  wertSize: 42, untertitelSize: 40
}

const FARBE = {
  hintergrund: '#e1ebea', text: '#1d1d1b', anteil: '#9b0a3c', rest: '#8a9396', trenner: '#e1ebea', flagge: '#d52b1e'
}

const DEFAULTS = Object.freeze({ titel: 'Wahlbeteiligung', flagge: true, wert: null, nachkommastellen: 1, untertitel: '' })

const FONT_FAMILY = 'Wahlen Text'
const FONT_FALLBACK = '"SRG SSR Type Text", "SRG SSR Type", "Helvetica Neue", Arial, sans-serif'

const R_MITTE = (L.aussen + L.innen) / 2
const BREITE = L.aussen - L.innen

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
  svg.ring { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; overflow: visible; }
  .wert { position: absolute; transform: translate(-50%, -50%); color: #fff; font-weight: 700; font-size: ${L.wertSize}px; white-space: nowrap;
          font-variant-numeric: tabular-nums; opacity: 0; }
  .untertitel { position: absolute; left: ${L.mitteX + L.aussen + 90}px; top: ${L.mitteY - 30}px; font-size: ${L.untertitelSize}px;
                white-space: pre-line; line-height: 1.3; }
`

function istZahl (v) { return typeof v === 'number' && Number.isFinite(v) }

class Wahlbeteiligung extends HTMLElement {
  constructor () {
    super()
    this._data = { ...DEFAULTS }
    this._step = undefined
    this._sichtbar = false
    this._laufend = new Set()
    this._warteschlange = Promise.resolve()
    this._resizeObserver = null
  }

  async load (params) {
    this._data = this._normalisieren({ ...DEFAULTS, ...(params?.data || {}) })
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' })
    const umfang = `transform="rotate(-90 ${L.mitteX} ${L.mitteY})"`
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="stage">
        <div class="titel"><span class="t"></span>
          <svg viewBox="0 0 32 32" aria-hidden="true"><rect width="32" height="32" fill="${FARBE.flagge}"/>
            <path fill="#fff" d="M13 6h6v7h7v6h-7v7h-6v-7H6v-6h7z"/></svg></div>
        <svg class="ring" viewBox="0 0 ${W} ${H}">
          <circle class="rest" cx="${L.mitteX}" cy="${L.mitteY}" r="${R_MITTE}" fill="none" stroke="${FARBE.rest}"
                  stroke-width="${BREITE}" pathLength="100" ${umfang} stroke-dasharray="0 100"/>
          <circle class="anteil" cx="${L.mitteX}" cy="${L.mitteY}" r="${R_MITTE}" fill="none" stroke="${FARBE.anteil}"
                  stroke-width="${BREITE}" pathLength="100" ${umfang} stroke-dasharray="0 100"/>
          <line class="trenner t0" stroke="${FARBE.trenner}" stroke-width="3" opacity="0"/>
          <line class="trenner t1" stroke="${FARBE.trenner}" stroke-width="3" opacity="0"/>
        </svg>
        <div class="wert"></div>
        <div class="untertitel"></div>
      </div>`
    const q = s => this.shadowRoot.querySelector(s)
    this._stage = q('.stage')
    this._anteil = q('circle.anteil')
    this._rest = q('circle.rest')
    this._trenner = [q('.t0'), q('.t1')]
    this._wert = q('.wert')
    this._untertitel = q('.untertitel')
    this._textSetzen()
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
      const ziel = (Number.isInteger(params.goto) && params.goto >= 0)
        ? params.goto
        : (this._step ?? -1) + (Number.isInteger(params.delta) ? params.delta : 1)
      if (ziel >= 1 || !istZahl(this._data.wert)) {
        await this._aus(skip)
        return { statusCode: 200, statusMessage: 'Ausgeblendet', currentStep: undefined }
      }
      if (!this._sichtbar) await this._ein(skip)
      this._step = 0
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
      const alt = this._data.wert
      this._data = this._normalisieren({ ...this._data, ...(params.data || {}) })
      this._textSetzen()
      if (this._sichtbar && istZahl(this._data.wert) && this._data.wert !== alt) {
        await this._aufWert(istZahl(alt) ? alt : 0, this._data.wert, !!params.skipAnimation)
      }
      return { statusCode: 200, statusMessage: 'Aktualisiert' }
    })
  }

  customAction (params = {}) {
    return Promise.resolve({ statusCode: 400, statusMessage: `Unbekannte customAction: ${params.id}` })
  }

  // ---------------- Aufbau ----------------

  _normalisieren (d) {
    const n = { ...d }
    const w = typeof n.wert === 'string' ? parseFloat(n.wert) : n.wert
    n.wert = istZahl(w) ? Math.max(0, Math.min(100, w)) : null
    n.nachkommastellen = d.nachkommastellen === undefined ? 1 : Math.max(0, Math.min(1, parseInt(n.nachkommastellen, 10) || 0))
    n.flagge = n.flagge !== false
    n.untertitel = String(n.untertitel ?? '')
    return n
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
    if (!this.shadowRoot) return
    this.shadowRoot.querySelector('.titel .t').textContent = this._data.titel || ''
    this.shadowRoot.querySelector('.titel svg').toggleAttribute('hidden', !this._data.flagge)
    this._untertitel.textContent = this._data.untertitel
    const w = this._data.wert
    this._wert.textContent = istZahl(w) ? `${w.toFixed(this._data.nachkommastellen)}%` : ''
    if (istZahl(w)) this._wertPosition(w)
  }

  // Wert mitten in den roten Teil setzen; Trennlinien an 12 Uhr und am Ende des roten Teils
  _wertPosition (w) {
    const winkel = (w / 100) * Math.PI          // Mitte des roten Bogens, von 12 Uhr aus
    this._wert.style.left = `${L.mitteX + R_MITTE * Math.sin(winkel)}px`
    this._wert.style.top = `${L.mitteY - R_MITTE * Math.cos(winkel)}px`
    const linie = (el, anteil) => {
      const a = anteil / 100 * 2 * Math.PI
      el.setAttribute('x1', L.mitteX + (L.innen - 1) * Math.sin(a)); el.setAttribute('y1', L.mitteY - (L.innen - 1) * Math.cos(a))
      el.setAttribute('x2', L.mitteX + (L.aussen + 1) * Math.sin(a)); el.setAttribute('y2', L.mitteY - (L.aussen + 1) * Math.cos(a))
    }
    linie(this._trenner[0], 0)
    linie(this._trenner[1], w)
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

  async _ein (skip) {
    const w = this._data.wert
    this._textSetzen()
    this._anteil.style.strokeDasharray = '0 100'
    this._rest.style.strokeDasharray = '0 100'
    this._rest.style.strokeDashoffset = `${-w}`
    this._wert.style.opacity = '0'
    this._trenner.forEach(t => { t.style.opacity = '0' })
    this._stage.style.opacity = '1'
    this._sichtbar = true
    if (!skip) {
      await this._anim(this._stage, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, easing: 'linear' }, false)
    }
    await Promise.all([
      this._anim(this._anteil, [{ strokeDasharray: '0 100' }, { strokeDasharray: `${w} 100` }],
        { duration: 800, delay: 400, easing: 'cubic-bezier(0.45, 0, 0.35, 1)' }, skip),
      this._anim(this._wert, [{ opacity: 0 }, { opacity: 1 }], { duration: 250, delay: 1000, easing: 'linear' }, skip),
      this._anim(this._rest, [{ strokeDasharray: '0 100' }, { strokeDasharray: `${100 - w} 100` }],
        { duration: 450, delay: 1250, easing: 'cubic-bezier(0.2, 0.7, 0.3, 1)' }, skip),
      ...this._trenner.map(t => this._anim(t, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 1650, easing: 'linear' }, skip))
    ])
  }

  async _aufWert (alt, neu, skip) {
    await Promise.all([
      this._anim(this._anteil, [{ strokeDasharray: `${alt} 100` }, { strokeDasharray: `${neu} 100` }], { duration: 600, easing: 'ease-in-out' }, skip),
      this._anim(this._rest, [{ strokeDasharray: `${100 - alt} 100`, strokeDashoffset: `${-alt}` },
        { strokeDasharray: `${100 - neu} 100`, strokeDashoffset: `${-neu}` }], { duration: 600, easing: 'ease-in-out' }, skip)
    ])
  }

  async _aus (skip) {
    if (!this._sichtbar) { this._step = undefined; return }
    await this._anim(this._stage, [{ opacity: 1 }, { opacity: 0 }], { duration: 250, easing: 'linear' }, skip)
    this._stage.style.opacity = '0'
    this._sichtbar = false
    this._step = undefined
  }
}

export default Wahlbeteiligung
