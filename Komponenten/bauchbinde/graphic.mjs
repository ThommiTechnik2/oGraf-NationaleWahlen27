/**
 * Wahlen 2027 – Bauchbinde
 * OGraf-Grafik nach EBU OGraf v1 (https://ograf.ebu.io/v1/specification/docs/Specification.html)
 *
 * Aufbau (Referenz: SRF Wahlen 2023, unten links, ab Bildrand):
 *   [ Lukas Golder ]                       <- Zeile 1: weiss auf Rot, Box passt sich der Textbreite an
 *   [ Politikwissenschafter GFS Bern ]     <- Zeile 2: dunkel auf Hellgrau (optional)
 *
 * Schritte (stepCount 1): playAction zeigt die Bauchbinde, ein weiterer playAction blendet aus
 * (currentStep undefined). stopAction blendet aus. updateAction tauscht den Text (auch auf Sendung).
 *
 * Animationen (aus der Referenz Bild für Bild gemessen, 1920x1080):
 *   Ein (≈520 ms): weisse Kontur der Namensbox zeichnet sich – rechte Kante von unten (0–60 ms),
 *     Unterkante von rechts nach links (30–170 ms), Oberkante von links nach rechts (180–380 ms);
 *     graue Box wischt von links ein (260–360 ms), Funktion blendet ein (330–430 ms);
 *     rote Fläche und Name blenden ein (370–500 ms), die Kontur verschwindet dabei (420–520 ms).
 *   Aus (≈130 ms): Zeile 2 blendet aus (0–90 ms), Zeile 1 (30–130 ms).
 */

const W = 1920
const H = 1080

// Layout in Pixeln bei 1920x1080
const L = {
  unten: 1037,        // Unterkante der untersten Box
  nameH: 102,
  nameSize: 76,
  nameVersatz: -3,    // Feinkorrektur Grundlinie Name (gemessen: Grundlinie 75 px unter Boxoberkante)
  funktionH: 59,
  funktionSize: 44,
  funktionVersatz: 0,
  textLinks: 86,      // Text beginnt bei x≈90 (Titelsicherheit), Box ab Bildrand
  textRechts: 28,
  maxBreite: 1720,    // längere Texte werden schmaler gesetzt
  kontur: 3
}

const FARBE = {
  name: '#a80a18',
  nameText: '#ffffff',
  funktion: '#e0e0e0',
  funktionText: '#212121',
  kontur: '#ffffff'
}

const DEFAULTS = Object.freeze({
  zeile1: '',
  zeile2: '',
  farbe: FARBE.name
})

const FONT_FAMILY = 'Wahlen Text'
const FONT_FALLBACK = '"SRG SSR Type Text", "SRG SSR Type", "Helvetica Neue", Arial, sans-serif'

const CSS = `
  :host { display: block; position: relative; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .stage { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; transform-origin: 0 0; overflow: hidden;
           font-family: "${FONT_FAMILY}", ${FONT_FALLBACK}; -webkit-font-smoothing: antialiased; font-weight: 400; }
  .box { position: absolute; left: 0; overflow: hidden; white-space: nowrap; padding: 0 ${L.textRechts}px 0 ${L.textLinks}px; visibility: hidden; }
  .name { height: ${L.nameH}px; }
  .funktion { top: ${L.unten - L.funktionH}px; height: ${L.funktionH}px; }
  .flaeche { position: absolute; inset: 0; }
  .name .flaeche { background: ${FARBE.name}; }
  .funktion .flaeche { background: ${FARBE.funktion}; }
  .txt { position: relative; display: inline-block; }
  .name .txt { color: ${FARBE.nameText}; font-size: ${L.nameSize}px; line-height: ${L.nameH}px; top: ${L.nameVersatz}px; }
  .funktion .txt { color: ${FARBE.funktionText}; font-size: ${L.funktionSize}px; line-height: ${L.funktionH}px; top: ${L.funktionVersatz}px; }
  .linie { position: absolute; background: ${FARBE.kontur}; opacity: 0; }
  .l-rechts { right: 0; top: 0; width: ${L.kontur}px; height: 100%; transform-origin: 50% 100%; }
  .l-unten { left: 0; bottom: 0; height: ${L.kontur}px; width: 100%; transform-origin: 100% 50%; }
  .l-oben { left: 0; top: 0; height: ${L.kontur}px; width: 100%; transform-origin: 0% 50%; }
`

class Bauchbinde extends HTMLElement {
  constructor () {
    super()
    this._data = { ...DEFAULTS }
    this._step = undefined
    this._sichtbar = false
    this._laufend = new Set()
    this._warteschlange = Promise.resolve()
    this._resizeObserver = null
  }

  // ---------------- OGraf: Pflichtmethoden ----------------

  async load (params) {
    this._data = this._normalisieren({ ...DEFAULTS, ...(params?.data || {}) })
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' })
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="stage">
        <div class="box name"><div class="flaeche"></div><span class="txt"></span>
          <i class="linie l-rechts"></i><i class="linie l-unten"></i><i class="linie l-oben"></i></div>
        <div class="box funktion"><div class="flaeche"></div><span class="txt"></span></div>
      </div>`
    const q = s => this.shadowRoot.querySelector(s)
    this._stage = q('.stage')
    this._name = q('.name')
    this._nameFlaeche = q('.name .flaeche')
    this._nameText = q('.name .txt')
    this._linien = { rechts: q('.l-rechts'), unten: q('.l-unten'), oben: q('.l-oben') }
    this._funktion = q('.funktion')
    this._funktionText = q('.funktion .txt')
    this._skalieren()
    this._resizeObserver = new ResizeObserver(() => this._skalieren())
    this._resizeObserver.observe(this)
    await this._schriftenLaden()
    this._textSetzen()
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
      if (ziel >= 1 || !this._data.zeile1) {
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
      const neu = this._normalisieren({ ...this._data, ...(params.data || {}) })
      const gleich = ['zeile1', 'zeile2', 'farbe'].every(k => neu[k] === this._data[k])
      this._data = neu
      if (!this._sichtbar) { this._textSetzen(); return { statusCode: 200, statusMessage: 'Aktualisiert' } }
      if (gleich) return { statusCode: 200, statusMessage: 'Unverändert' }
      if (!neu.zeile1) { await this._aus(!!params.skipAnimation); return { statusCode: 200, statusMessage: 'Leer, ausgeblendet' } }
      await this._wechseln(!!params.skipAnimation)
      return { statusCode: 200, statusMessage: 'Aktualisiert' }
    })
  }

  customAction (params = {}) {
    return Promise.resolve({ statusCode: 400, statusMessage: `Unbekannte customAction: ${params.id}` })
  }

  // ---------------- Aufbau ----------------

  _normalisieren (d) {
    const n = { ...d }
    n.zeile1 = String(n.zeile1 ?? '').trim()
    n.zeile2 = String(n.zeile2 ?? '').trim()
    n.farbe = /^#[0-9a-fA-F]{6}$/.test(n.farbe || '') ? n.farbe.toLowerCase() : FARBE.name
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
    // Schriften optional aus fonts/fonts.json. Fehlende Dateien werden übersprungen (Rückfall: Systemschrift).
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
        } catch (e) { /* Datei fehlt oder ungültig: Rückfallschrift */ }
      }))
    } catch (e) { /* keine fonts.json */ }
  }

  // Text, Farbe und Lage setzen. Ohne Zeile 2 rutscht die Namensbox auf die Unterkante.
  _textSetzen () {
    const d = this._data
    this._nameText.textContent = d.zeile1
    this._funktionText.textContent = d.zeile2
    this._nameFlaeche.style.background = d.farbe
    this._funktion.style.display = d.zeile2 ? '' : 'none'
    const nameTop = d.zeile2 ? L.unten - L.funktionH - L.nameH : L.unten - L.nameH
    this._name.style.top = `${nameTop}px`
    this._einpassen(this._name, this._nameText, L.nameSize)
    this._einpassen(this._funktion, this._funktionText, L.funktionSize)
  }

  // Zu lange Texte schmaler setzen, damit die Box nicht über maxBreite hinausgeht
  _einpassen (box, txt, groesse) {
    txt.style.fontSize = `${groesse}px`
    let s = groesse
    while (box.offsetWidth > L.maxBreite && s > groesse * 0.6) {
      s -= 1
      txt.style.fontSize = `${s}px`
    }
  }

  // ---------------- Animationen ----------------

  _anim (el, keyframes, optionen, skip) {
    const a = el.animate(keyframes, { fill: 'forwards', ...optionen, ...(skip ? { duration: 0, delay: 0 } : {}) })
    this._laufend.add(a)
    return a.finished.then(() => {
      try { a.commitStyles() } catch (e) { /* Element nicht mehr im DOM */ }
      a.cancel()
    }).catch(() => {}).finally(() => this._laufend.delete(a))
  }

  _alleAnimationenBeenden () {
    for (const a of [...this._laufend]) { try { a.finish() } catch (e) { /* bereits beendet */ } }
  }

  _einreihen (fn) {
    const p = this._warteschlange.then(fn, fn)
    this._warteschlange = p.catch(() => {})
    return p.catch(e => ({ statusCode: 500, statusMessage: String(e && e.message ? e.message : e) }))
  }

  _startzustand () {
    this._name.style.opacity = '1'
    this._funktion.style.opacity = '1'
    this._nameFlaeche.style.opacity = '0'
    this._nameText.style.opacity = '0'
    this._funktionText.style.opacity = '0'
    this._funktion.style.clipPath = 'inset(0 100% 0 0)'
    this._linien.rechts.style.transform = 'scaleY(0)'
    this._linien.unten.style.transform = 'scaleX(0)'
    this._linien.oben.style.transform = 'scaleX(0)'
    Object.values(this._linien).forEach(l => { l.style.opacity = '1' })
  }

  async _ein (skip) {
    this._textSetzen()
    this._startzustand()
    this._name.style.visibility = 'visible'
    this._funktion.style.visibility = 'visible'
    this._sichtbar = true
    const li = this._linien
    const mitFunktion = !!this._data.zeile2
    const laeufe = [
      this._anim(li.rechts, [{ transform: 'scaleY(0)' }, { transform: 'scaleY(1)' }], { duration: 60, easing: 'linear' }, skip),
      this._anim(li.unten, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 140, delay: 30, easing: 'ease-out' }, skip),
      this._anim(li.oben, [{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 200, delay: 180, easing: 'ease-in-out' }, skip),
      this._anim(this._nameFlaeche, [{ opacity: 0 }, { opacity: 1 }], { duration: 130, delay: 370, easing: 'linear' }, skip),
      this._anim(this._nameText, [{ opacity: 0 }, { opacity: 1 }], { duration: 130, delay: 370, easing: 'linear' }, skip),
      ...Object.values(li).map(l => this._anim(l, [{ opacity: 1 }, { opacity: 0 }], { duration: 100, delay: 420, easing: 'linear' }, skip))
    ]
    if (mitFunktion) {
      laeufe.push(
        this._anim(this._funktion, [{ clipPath: 'inset(0 100% 0 0)' }, { clipPath: 'inset(0 0% 0 0)' }], { duration: 100, delay: 260, easing: 'ease-out' }, skip),
        this._anim(this._funktionText, [{ opacity: 0 }, { opacity: 1 }], { duration: 100, delay: 330, easing: 'linear' }, skip))
    }
    await Promise.all(laeufe)
  }

  async _aus (skip) {
    if (!this._sichtbar) { this._step = undefined; return }
    await Promise.all([
      this._anim(this._funktion, [{ opacity: 1 }, { opacity: 0 }], { duration: 90, easing: 'linear' }, skip),
      this._anim(this._name, [{ opacity: 1 }, { opacity: 0 }], { duration: 100, delay: 30, easing: 'linear' }, skip)
    ])
    this._name.style.visibility = 'hidden'
    this._funktion.style.visibility = 'hidden'
    this._sichtbar = false
    this._step = undefined
  }

  // Auf Sendung neuer Text: Texte blenden aus, Boxen passen ihre Breite an, neue Texte blenden ein
  async _wechseln (skip) {
    const vorher = {
      nameW: this._name.offsetWidth, nameTop: this._name.offsetTop,
      funktionW: this._funktion.style.display === 'none' ? 0 : this._funktion.offsetWidth
    }
    await Promise.all([
      this._anim(this._nameText, [{ opacity: 1 }, { opacity: 0 }], { duration: 100, easing: 'linear' }, skip),
      this._anim(this._funktionText, [{ opacity: 1 }, { opacity: 0 }], { duration: 100, easing: 'linear' }, skip)
    ])
    this._textSetzen()
    const nachher = {
      nameW: this._name.offsetWidth, nameTop: this._name.offsetTop,
      funktionW: this._data.zeile2 ? this._funktion.offsetWidth : 0
    }
    const laeufe = [
      this._anim(this._name, [{ width: `${vorher.nameW}px`, top: `${vorher.nameTop}px` }, { width: `${nachher.nameW}px`, top: `${nachher.nameTop}px` }],
        { duration: 220, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' }, skip).then(() => { this._name.style.width = ''; this._name.style.top = `${nachher.nameTop}px` }),
      this._anim(this._nameText, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 200, easing: 'linear' }, skip)
    ]
    if (this._data.zeile2) {
      this._funktion.style.visibility = 'visible'
      this._funktion.style.opacity = '1'
      this._funktion.style.clipPath = 'inset(0 0% 0 0)'
      laeufe.push(
        this._anim(this._funktion, [{ width: `${vorher.funktionW}px` }, { width: `${nachher.funktionW}px` }],
          { duration: 220, easing: 'cubic-bezier(0.65, 0, 0.35, 1)' }, skip).then(() => { this._funktion.style.width = '' }),
        this._anim(this._funktionText, [{ opacity: 0 }, { opacity: 1 }], { duration: 150, delay: 200, easing: 'linear' }, skip))
    }
    await Promise.all(laeufe)
  }
}

export default Bauchbinde
