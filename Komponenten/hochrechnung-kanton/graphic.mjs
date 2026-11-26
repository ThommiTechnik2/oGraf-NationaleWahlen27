/**
 * Wahlen 2027 – Hochrechnung Kanton / Schweiz (Insert)
 * OGraf-Grafik nach EBU OGraf v1 (https://ograf.ebu.io/v1/specification/docs/Specification.html)
 *
 * Derselbe Code steckt in den Paketen «hochrechnung-kanton» und «hochrechnung-schweiz»
 * (jede oGraf-Grafik ist ein eigenständiges Paket). Änderungen bitte in beiden Ordnern übernehmen.
 *
 * Aufbau (Referenz: SRF Wahlen 2023, Insert unten rechts):
 *   Hochrechnung BS [Wappen]
 *   Nationalrat, 4 Sitze
 *   [SP ][Grüne][LDP ]      <- Kopf in Parteifarbe
 *   [ 1 ][  1  ][ 1  ]      <- Körper: Sitze bzw. Wähleranteil
 *   [-1 ][ ±0  ][ ±0 ]      <- Veränderung zur Vorwahl
 *
 * Schritte (stepCount -1, abhängig von der Anzahl Parteien):
 *   mit Sitzen:  Schritt 2n = Seite n Sitze, Schritt 2n+1 = Seite n Wähleranteil
 *   ohne Sitze:  Schritt n  = Seite n Wähleranteil
 *   playAction über den letzten Schritt hinaus blendet aus (currentStep undefined).
 *
 * Animationen (aus der Referenz Bild für Bild gemessen, 1920x1080):
 *   Ein:          Boxen fahren nacheinander von rechts ein (450 ms, Abstand 130 ms), dann Titel ein (260 ms)
 *   Sitze -> %:   Inhalt der Körper rollt nach oben (350 ms)
 *   Seite:        Köpfe tauchen hinter den Körper ab (200 ms), Werte wechseln, neue Köpfe tauchen auf (220 ms)
 *   Aus:          Titel aus (160 ms), Boxen fahren nach rechts hinaus (380 ms, rechte zuerst)
 */

const W = 1920
const H = 1080

// Einziger Unterschied zwischen den Paketen: Lage (gemessen an den SRF-Referenzen 2023).
// Kanton-Insert { x: 0, y: 0 }, Schweiz-Insert { x: -13, y: -10 } (Unterkante auf 1037 wie die Bauchbinde)
const VERSATZ = { x: 0, y: 0 }

// Layout in Pixeln bei 1920x1080
const L = {
  left: 1348 + VERSATZ.x,         // linke Kante der ersten Box und des Titels
  boxTop: 908 + VERSATZ.y,        // Oberkante der Parteiköpfe
  boxW: 128,
  gap: 22,
  headH: 56,
  bodyH: 82,
  titleTop: 789 + VERSATZ.y,
  titleSize: 44,
  titleLine: 49,
  headSize: 33,
  valueSize: 37,
  diffSize: 27,
  offRight: 640       // Strecke für Ein-/Ausfahren nach rechts
}

const FARBE = {
  koerper: '#E0E0E0',
  wert: '#1E1E1E',
  plus: '#2A78BE',
  minus: '#D0213C',
  null: '#4A4A4A'
}

const EASE_OUT = 'cubic-bezier(0.16, 1, 0.3, 1)'
const EASE_IN = 'cubic-bezier(0.55, 0, 1, 0.45)'
const EASE_IN_OUT = 'cubic-bezier(0.65, 0, 0.35, 1)'

const DEFAULTS = Object.freeze({
  titel: '',
  untertitel: '',
  kanton: '',
  mit_sitzen: true,
  nachkommastellen: 1,
  pro_seite: 3,
  seiten: [],         // optional: Anzahl Parteien je Seite, z. B. [3, 3, 2, 3]; Rest in Seiten zu «pro_seite»
  parteien: []
})

const FONT_FAMILY = 'Wahlen Text'
const FONT_FALLBACK = '"SRG SSR Type Text", "SRG SSR Type", "Helvetica Neue", Arial, sans-serif'

const CSS = `
  :host { display: block; position: relative; width: 100%; height: 100%; overflow: hidden; pointer-events: none; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  .stage { position: absolute; left: 0; top: 0; width: ${W}px; height: ${H}px; transform-origin: 0 0; overflow: hidden;
           font-family: "${FONT_FAMILY}", ${FONT_FALLBACK}; -webkit-font-smoothing: antialiased; }
  .titel { position: absolute; left: ${L.left}px; top: ${L.titleTop}px; color: #fff; opacity: 0;
           font-size: ${L.titleSize}px; line-height: ${L.titleLine}px; font-weight: 400; white-space: nowrap;
           text-shadow: 0 1px 4px rgba(0,0,0,0.45), 0 0 1px rgba(0,0,0,0.35); }
  .titel .zeile1 { display: flex; align-items: center; gap: 10px; }
  .titel img { height: 32px; width: auto; display: block; margin-top: -2px; }
  .titel img[hidden] { display: none; }
  .reihe { position: absolute; left: ${L.left}px; top: ${L.boxTop}px; height: ${L.headH + L.bodyH}px; }
  .box { position: absolute; top: 0; width: ${L.boxW}px; height: ${L.headH + L.bodyH}px; }
  .kopf { position: absolute; left: 0; top: 0; width: 100%; height: ${L.headH}px; z-index: 1; color: #fff;
          font-size: ${L.headSize}px; line-height: ${L.headH}px; font-weight: 600; text-align: center; white-space: nowrap; overflow: hidden; }
  .koerper { position: absolute; left: 0; top: ${L.headH}px; width: 100%; height: ${L.bodyH}px; z-index: 2;
             background: ${FARBE.koerper}; overflow: hidden; }
  .zelle { position: absolute; left: 0; top: 0; width: 100%; height: ${L.bodyH}px; text-align: center; }
  .wert { color: ${FARBE.wert}; font-size: ${L.valueSize}px; line-height: 44px; padding-top: 7px; font-variant-numeric: tabular-nums; }
  .diff { font-size: ${L.diffSize}px; line-height: 28px; font-variant-numeric: tabular-nums; }
  .diff.plus { color: ${FARBE.plus}; } .diff.minus { color: ${FARBE.minus}; } .diff.null { color: ${FARBE.null}; }
`

// ---------------------------------------------------------------------------
// Formatierung
// ---------------------------------------------------------------------------
function istZahl (v) { return typeof v === 'number' && Number.isFinite(v) }

function formatSitze (p) {
  return { wert: istZahl(p.sitze) ? String(p.sitze) : '–', diff: formatDiff(p.sitze_diff, 0, '') }
}

function formatProzent (p, stellen) {
  return { wert: istZahl(p.staerke) ? `${p.staerke.toFixed(stellen)}%` : '–', diff: formatDiff(p.staerke_diff, stellen, '%', p.staerke_diff_unsicher) }
}

// unsicher: Veränderung liegt im Fehlerbereich der Hochrechnung → «±» statt Vorzeichen (wie SRF 2023)
function formatDiff (v, stellen, einheit, unsicher = false) {
  if (!istZahl(v)) return { text: '', klasse: 'null' }
  const gerundet = Number(v.toFixed(stellen))
  if (gerundet === 0 || unsicher) return { text: `±${Math.abs(gerundet).toFixed(stellen)}${einheit}`, klasse: 'null' }
  const zeichen = gerundet > 0 ? '+' : '-'
  return { text: `${zeichen}${Math.abs(gerundet).toFixed(stellen)}${einheit}`, klasse: gerundet > 0 ? 'plus' : 'minus' }
}

// ---------------------------------------------------------------------------
// Grafik
// ---------------------------------------------------------------------------
class HochrechnungKanton extends HTMLElement {
  constructor () {
    super()
    this._data = { ...DEFAULTS }
    this._step = undefined          // undefined = Startzustand (nichts sichtbar)
    this._sichtbar = false
    this._seite = 0
    this._ansicht = 'sitze'         // 'sitze' | 'prozent'
    this._boxen = []
    this._laufend = new Set()       // laufende Web-Animationen
    this._warteschlange = Promise.resolve()
    this._resizeObserver = null
  }

  // ---------------- OGraf: Pflichtmethoden ----------------

  async load (params) {
    this._data = this._normalisieren({ ...DEFAULTS, ...(params?.data || {}) })
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' })
    this.shadowRoot.innerHTML = `<style>${CSS}</style>
      <div class="stage">
        <div class="titel"><div class="zeile1"><span class="t1"></span><img alt="" hidden></div><div class="t2"></div></div>
        <div class="reihe"></div>
      </div>`
    this._stage = this.shadowRoot.querySelector('.stage')
    this._titel = this.shadowRoot.querySelector('.titel')
    this._reihe = this.shadowRoot.querySelector('.reihe')
    this._wappen = this.shadowRoot.querySelector('.titel img')
    this._skalieren()
    this._resizeObserver = new ResizeObserver(() => this._skalieren())
    this._resizeObserver.observe(this)
    await Promise.all([this._schriftenLaden(), this._titelSetzen()])
    return { statusCode: 200, statusMessage: 'Geladen' }
  }

  async dispose () {
    this._alleAnimationenBeenden()
    if (this._resizeObserver) this._resizeObserver.disconnect()
    if (this.shadowRoot) this.shadowRoot.innerHTML = ''
    this._boxen = []
    return { statusCode: 200, statusMessage: 'Entladen' }
  }

  playAction (params = {}) {
    return this._einreihen(() => this._play(params))
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
      const alt = this._data
      this._data = neu
      await this._titelSetzen()
      if (this._sichtbar) {
        const maxStep = this._anzahlSchritte() - 1
        if (maxStep < 0) {
          await this._aus(!!params.skipAnimation)
        } else {
          const step = Math.min(this._step ?? 0, maxStep)
          const { seite, ansicht } = this._stepZuZustand(step)
          this._step = step
          const parteienGeaendert = this._seitenSchluessel(alt, seite) !== this._seitenSchluessel(neu, seite)
          if (parteienGeaendert || seite !== this._seite) {
            await this._seiteWechseln(seite, ansicht, !!params.skipAnimation)
          } else {
            await this._werteRollen(ansicht, !!params.skipAnimation, true)
          }
        }
      }
      return { statusCode: 200, statusMessage: 'Aktualisiert' }
    })
  }

  customAction (params = {}) {
    return Promise.resolve({ statusCode: 400, statusMessage: `Unbekannte customAction: ${params.id}` })
  }

  // ---------------- Schritte ----------------

  async _play ({ goto, delta, skipAnimation } = {}) {
    const skip = !!skipAnimation
    const gesamt = this._anzahlSchritte()
    let ziel = (Number.isInteger(goto) && goto >= 0)
      ? goto
      : (this._step ?? -1) + (Number.isInteger(delta) ? delta : 1)
    if (ziel < 0) ziel = 0
    if (gesamt === 0 || ziel >= gesamt) {
      await this._aus(skip)
      return { statusCode: 200, statusMessage: 'Ende erreicht, ausgeblendet', currentStep: undefined }
    }
    const { seite, ansicht } = this._stepZuZustand(ziel)
    if (!this._sichtbar) {
      await this._ein(seite, ansicht, skip)
    } else if (seite !== this._seite) {
      await this._seiteWechseln(seite, ansicht, skip)
    } else if (ansicht !== this._ansicht) {
      await this._werteRollen(ansicht, skip, false)
    }
    this._step = ziel
    return { statusCode: 200, statusMessage: 'OK', currentStep: ziel }
  }

  _ansichtenProSeite () { return this._data.mit_sitzen ? 2 : 1 }
  // Seitengrenzen [[start, ende), ...] aus «seiten» (redaktionell) bzw. «pro_seite»
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

  _anzahlSeiten () { return this._grenzen().length }
  _anzahlSchritte () { return this._anzahlSeiten() * this._ansichtenProSeite() }

  _stepZuZustand (step) {
    const n = this._ansichtenProSeite()
    return { seite: Math.floor(step / n), ansicht: n === 2 && step % 2 === 0 ? 'sitze' : 'prozent' }
  }

  _parteienDerSeite (seite, data = this._data) {
    const g = this._grenzen(data)[seite]
    return g ? data.parteien.slice(g[0], g[1]) : []
  }

  _seitenSchluessel (data, seite) {
    return this._parteienDerSeite(seite, data).map(p => `${p.kurz}|${p.farbe}`).join(',')
  }

  // ---------------- Aufbau ----------------

  _normalisieren (d) {
    const n = { ...d }
    n.pro_seite = Math.max(1, Math.min(3, parseInt(n.pro_seite, 10) || 3))
    n.nachkommastellen = Math.max(0, Math.min(1, parseInt(n.nachkommastellen, 10) || 0))
    if (d.nachkommastellen === undefined) n.nachkommastellen = 1
    n.mit_sitzen = n.mit_sitzen !== false
    n.parteien = Array.isArray(n.parteien) ? n.parteien.filter(p => p && p.kurz) : []
    n.seiten = Array.isArray(n.seiten) ? n.seiten.map(x => parseInt(x, 10)).filter(x => x >= 1 && x <= 3) : []
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

  _titelSetzen () {
    this.shadowRoot.querySelector('.t1').textContent = this._data.titel || ''
    this.shadowRoot.querySelector('.t2').textContent = this._data.untertitel || ''
    const kt = (this._data.kanton || '').trim()
    const img = this._wappen
    if (!kt) { img.hidden = true; img.removeAttribute('src'); return Promise.resolve() }
    return new Promise(resolve => {
      const versuche = ['svg', 'png']
      const naechster = () => {
        const ext = versuche.shift()
        if (!ext) { img.hidden = true; resolve(); return }
        img.onload = () => { img.hidden = false; resolve() }
        img.onerror = naechster
        img.src = new URL(`./wappen/${kt}.${ext}`, import.meta.url).href
      }
      naechster()
    })
  }

  _boxErstellen (index) {
    const box = document.createElement('div')
    box.className = 'box'
    box.style.left = `${index * (L.boxW + L.gap)}px`
    box.innerHTML = '<div class="kopf"></div><div class="koerper"></div>'
    this._reihe.appendChild(box)
    return box
  }

  _kopfSetzen (box, partei) {
    const kopf = box.querySelector('.kopf')
    kopf.textContent = partei.kurz
    kopf.style.background = partei.farbe
  }

  _zelleErstellen (partei, ansicht) {
    const f = ansicht === 'sitze' ? formatSitze(partei) : formatProzent(partei, this._data.nachkommastellen)
    const z = document.createElement('div')
    z.className = 'zelle'
    z.innerHTML = `<div class="wert"></div><div class="diff ${f.diff.klasse}"></div>`
    z.querySelector('.wert').textContent = f.wert
    z.querySelector('.diff').textContent = f.diff.text
    return z
  }

  _koerperSetzen (box, partei, ansicht) {
    const k = box.querySelector('.koerper')
    k.innerHTML = ''
    k.appendChild(this._zelleErstellen(partei, ansicht))
  }

  _reiheAufbauen (seite, ansicht) {
    this._reihe.innerHTML = ''
    this._boxen = this._parteienDerSeite(seite).map((p, i) => {
      const box = this._boxErstellen(i)
      this._kopfSetzen(box, p)
      this._koerperSetzen(box, p, ansicht)
      return box
    })
    this._seite = seite
    this._ansicht = ansicht
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

  async _ein (seite, ansicht, skip) {
    this._reiheAufbauen(seite, ansicht)
    this._titel.style.opacity = '0'
    this._titel.style.transform = 'translateY(10px)'
    this._boxen.forEach(b => { b.style.transform = `translateX(${L.offRight}px)` })
    this._sichtbar = true
    const laeufe = this._boxen.map((b, i) => this._anim(b,
      [{ transform: `translateX(${L.offRight}px)` }, { transform: 'translateX(0px)' }],
      { duration: 450, delay: i * 130, easing: EASE_OUT }, skip))
    laeufe.push(this._anim(this._titel,
      [{ opacity: 0, transform: 'translateY(10px)' }, { opacity: 1, transform: 'translateY(0px)' }],
      { duration: 260, delay: 280, easing: 'ease-out' }, skip))
    await Promise.all(laeufe)
  }

  async _aus (skip) {
    if (!this._sichtbar) { this._step = undefined; return }
    const n = this._boxen.length
    const laeufe = [this._anim(this._titel, [{ opacity: 1 }, { opacity: 0 }], { duration: 160, easing: 'linear' }, skip)]
    this._boxen.forEach((b, i) => laeufe.push(this._anim(b,
      [{ transform: 'translateX(0px)' }, { transform: `translateX(${L.offRight}px)` }],
      { duration: 380, delay: 100 + (n - 1 - i) * 60, easing: EASE_IN }, skip)))
    await Promise.all(laeufe)
    this._reihe.innerHTML = ''
    this._boxen = []
    this._sichtbar = false
    this._step = undefined
  }

  // Inhalt der Körper rollt nach oben zur neuen Ansicht (oder zu neuen Werten derselben Ansicht)
  async _werteRollen (ansicht, skip, nurBeiAenderung) {
    const parteien = this._parteienDerSeite(this._seite)
    const laeufe = []
    this._boxen.forEach((box, i) => {
      const p = parteien[i]
      if (!p) return
      this._kopfSetzen(box, p)
      const k = box.querySelector('.koerper')
      const alt = k.querySelector('.zelle:last-child')
      const neu = this._zelleErstellen(p, ansicht)
      if (nurBeiAenderung && alt && alt.innerHTML === neu.innerHTML) return
      neu.style.transform = `translateY(${L.bodyH}px)`
      k.appendChild(neu)
      if (alt) {
        laeufe.push(this._anim(alt, [{ transform: 'translateY(0px)' }, { transform: `translateY(${-L.bodyH}px)` }],
          { duration: 350, easing: EASE_IN_OUT }, skip).then(() => alt.remove()))
      }
      laeufe.push(this._anim(neu, [{ transform: `translateY(${L.bodyH}px)` }, { transform: 'translateY(0px)' }],
        { duration: 350, easing: EASE_IN_OUT }, skip))
    })
    this._ansicht = ansicht
    await Promise.all(laeufe)
  }

  // Köpfe tauchen ab, Werte wechseln, neue Köpfe tauchen auf. Mehr/weniger Boxen fahren rechts ein/aus.
  async _seiteWechseln (seite, ansicht, skip) {
    const neueParteien = this._parteienDerSeite(seite)
    const alte = this._boxen
    // 1. Köpfe abtauchen
    await Promise.all(alte.map(b => this._anim(b.querySelector('.kopf'),
      [{ transform: 'translateY(0px)' }, { transform: `translateY(${L.headH}px)` }],
      { duration: 200, easing: EASE_IN }, skip)))
    // 2. überzählige Boxen ausfahren, Werte der bleibenden Boxen wechseln
    const bleibend = alte.slice(0, neueParteien.length)
    const weg = alte.slice(neueParteien.length)
    const laeufe = weg.map((b, i) => this._anim(b,
      [{ transform: 'translateX(0px)' }, { transform: `translateX(${L.offRight}px)` }],
      { duration: 300, delay: i * 40, easing: EASE_IN }, skip).then(() => b.remove()))
    bleibend.forEach((b, i) => {
      this._kopfSetzen(b, neueParteien[i])
      const k = b.querySelector('.koerper')
      k.innerHTML = ''
      const z = this._zelleErstellen(neueParteien[i], ansicht)
      k.appendChild(z)
      laeufe.push(this._anim(z, [{ opacity: 0 }, { opacity: 1 }], { duration: 100, easing: 'linear' }, skip))
    })
    // 3. zusätzliche Boxen von rechts einfahren
    const neu = []
    for (let i = bleibend.length; i < neueParteien.length; i++) {
      const box = this._boxErstellen(i)
      this._kopfSetzen(box, neueParteien[i])
      this._koerperSetzen(box, neueParteien[i], ansicht)
      box.style.transform = `translateX(${L.offRight}px)`
      neu.push(box)
      laeufe.push(this._anim(box, [{ transform: `translateX(${L.offRight}px)` }, { transform: 'translateX(0px)' }],
        { duration: 450, delay: (i - bleibend.length) * 130, easing: EASE_OUT }, skip))
    }
    // 4. Köpfe auftauchen
    laeufe.push(...bleibend.map(b => this._anim(b.querySelector('.kopf'),
      [{ transform: `translateY(${L.headH}px)` }, { transform: 'translateY(0px)' }],
      { duration: 220, delay: 80, easing: EASE_OUT }, skip)))
    await Promise.all(laeufe)
    this._boxen = [...bleibend, ...neu]
    this._seite = seite
    this._ansicht = ansicht
  }
}

export default HochrechnungKanton
