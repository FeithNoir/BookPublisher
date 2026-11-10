// Tema «Códice»: tratado antiguo. Reproduce el estilo del Manual de Arbitraje y
// del Libro del Grupo Armagedón: pergamino, EB Garamond + IM Fell English,
// versalitas espaciadas, filetes con rombo, capítulos en romanos, índice con
// puntos guía, cruz † y «Pendiente de consultar» en rojo.
#import "../_lib/common.typ": *
#import "../_lib/droplet/lib.typ": dropcap

#let paper = rgb("#f1e7d0")
#let ink = rgb("#2e2418")
#let red = rgb("#8c2f1b")
#let muted = rgb("#726858")
#let rulec = rgb("#aca28f")
#let shade = rgb("#e9dec5")
#let headbg = rgb("#e3d5b8")
#let serif = ("EB Garamond", "Libertinus Serif")
#let fell = ("IM FELL English", "EB Garamond")

#let spaced(body, size: 9pt, fill: muted, tracking: 0.28em) = text(
  size: size, fill: fill, tracking: tracking, upper(body),
)

#let diamond(size: 7pt, fill: red) = box(baseline: -0.5pt, polygon(
  fill: fill,
  (size / 2, 0pt), (size, size / 2), (size / 2, size), (0pt, size / 2),
))

#let ornament-rule(width: 70%) = align(center, block(width: width, grid(
  columns: (1fr, auto, 1fr), column-gutter: 8pt, align: horizon,
  line(length: 100%, stroke: 0.6pt + muted), diamond(), line(length: 100%, stroke: 0.6pt + muted),
)))

#let running-title(meta) = {
  let h = meta.at("header", default: none)
  if h == none { meta.at("title", default: "") } else { h }
}

// ------------------------------------------------------------------ cuerpo
#let setup(meta, front: false, body) = {
  let (pw, ph) = page-dims(meta, "a4")
  let size = opt(meta, "font_size", 12.4) * 1pt
  // Geometría medida en los PDF originales (A4): texto a 75 pt de cada lado,
  // primera línea base a 56 pt, cabecera en 30 pt y folio en 820 pt.
  set page(
    width: pw, height: ph, fill: paper,
    margin: (top: 48pt, bottom: 46pt, x: 75pt),
    header-ascent: 0pt,
    footer-descent: 0pt,
    header: context {
      if is-blank-page() { return }
      place(top + center, dy: 22pt, spaced(size: 8.5pt, tracking: 0.24em)[·#h(0.9em)#running-title(meta)#h(0.9em)·])
    },
    footer: context {
      if is-blank-page() { return }
      let n = counter(page).get().first()
      place(top + center, dy: 20pt, text(size: 11pt, fill: ink, tracking: 0.12em,
        if front { numbering("i", n) } else { str(n) }))
    },
  )
  set text(font: serif, size: size, fill: ink, lang: opt(meta, "lang", "es"),
    hyphenate: opt(meta, "hyphenate", true), number-type: "old-style")
  set smartquote(quotes: bp-quotes(meta))
  set par(justify: true, leading: 1.02em, spacing: 1.83em, first-line-indent: 0pt,
    justification-limits: (tracking: (min: -0.01em, max: 0.02em), spacing: (min: 80%, max: 140%)))
  show "†": set text(fill: red)
  set list(marker: ([#diamond(size: 5.5pt)], [#text(fill: red)[–]]), indent: 0pt, body-indent: 7.5pt, spacing: 1.6em)
  set enum(numbering: n => text(fill: red, numbering("1.", n)), indent: 0.2em, body-indent: 0.6em)
  set footnote.entry(separator: line(length: 25%, stroke: 0.5pt + muted))
  show footnote.entry: set text(size: 0.82em)
  show heading.where(level: 2): it => block(above: 2.1em, below: 1.25em, sticky: true,
    text(size: 1.145em, weight: 600, tracking: 0.03em)[#diamond(size: 6.5pt)#h(0.5em)#it.body])
  show heading.where(level: 3): it => block(above: 1.3em, below: 0.8em, sticky: true,
    text(style: "italic", size: 1.04em, weight: 500)[#it.body])
  show heading.where(level: 4): it => block(above: 1.1em, below: 0.6em, sticky: true,
    smallcaps(text(weight: 600)[#it.body]))
  show quote.where(block: true): it => pad(x: 2.2em, block(text(style: "italic", it.body)))
  show raw: set text(font: ("DejaVu Sans Mono",), size: 0.85em)
  show link: set text(fill: red)
  body
}

#let chapter-opening(ch, meta) = {
  let label = ch.at("label", default: none)
  let flow = opt(meta, "chapter_break", "flow") == "flow"
  // En el códice los anexos y el colofón abren página, como en los originales.
  if flow and ch.at("appendix", default: false) { pagebreak(weak: true); flow = false }
  block(above: if flow { 2.4em } else { 0pt }, below: 2.15em, sticky: true, width: 100%, {
    set align(center)
    [#metadata(ch) <bp-chapter>]
    v(if flow { 0pt } else { 30pt })
    if label != none {
      block(below: 1.05em, spaced(size: 9.8pt, fill: red, tracking: 0.32em, label))
    }
    if ch.at("title", default: none) != none {
      block(below: 0.75em, text(font: fell, size: 23.2pt, hyphenate: false,
        { set par(leading: 0.42em, justify: false); ch.title }))
    }
    ornament-rule(width: 76%)
  })
}

#let first-paragraph(body, letter: none, rest: none, meta: (:)) = {
  if letter == none or not opt(meta, "dropcaps", true) { body } else {
    dropcap(height: 33pt, gap: 8pt, fill: red, font: fell, letter, rest)
  }
}

#let pendiente(body) = text(fill: red, style: "italic",
  underline(stroke: (paint: red, thickness: 0.6pt, dash: "dotted"), offset: 2.6pt, evade: false, body))

#let span(cls, body) = if cls == "pendiente" { pendiente(body) } else if cls == "propuesta" {
  text(fill: red, body)
} else { body }

#let lead(body) = smallcaps(strong(body))

#let callout(kind, title, body) = block(width: 100%, fill: shade, stroke: 0.6pt + muted,
  inset: (x: 14pt, y: 12pt), above: 1.4em, below: 1.4em, {
    set par(leading: 0.7em)
    if title != none [#smallcaps(all: false, text(tracking: 0.04em, title)) ]
    else if kind != "nota" [#smallcaps(upper(kind.first()) + kind.slice(1) + ".") ]
    body
  })

#let table-block(header, rows, aligns) = {
  let n = header.len()
  let al = aligns.map(a => if a == "center" { center } else if a == "right" { right } else { left })
  set par(leading: 0.62em, justify: false)
  block(above: 1.3em, below: 1.6em, table(
    columns: n, stroke: 0.6pt + muted, inset: (x: 8pt, y: 7pt),
    fill: (_, y) => if y == 0 { headbg } else if calc.even(y) { shade } else { none },
    // Las filas se leen mejor con interlineado propio, más apretado que el del cuerpo.
    align: (x, y) => al.at(x, default: left) + top,
    table.header(..header.map(c => smallcaps(all: false, text(weight: 600, size: 0.85em, tracking: 0.05em, c)))),
    ..rows.flatten().map(c => text(size: 0.88em, c)),
  ))
}

#let figure-image(path, caption) = figure(image(path, width: 80%),
  caption: if caption == none { none } else { text(style: "italic", size: 0.9em, caption) },
  supplement: none, numbering: none)

#let scene-break() = block(above: 1.4em, below: 1.4em, ornament-rule(width: 40%))

// --------------------------------------------------------------- portada
#let corner(flip-x: false, flip-y: false) = {
  let s = 14mm
  let c = curve(stroke: 0.9pt + ink, curve.move((0pt, s)), curve.cubic((0pt, 3mm), (3mm, 0pt), (s, 0pt)))
  scale(x: if flip-x { -100% } else { 100% }, y: if flip-y { -100% } else { 100% }, origin: center, c)
}

#let cover(meta) = {
  let (pw, ph) = page-dims(meta, "a4")
  set page(width: pw, height: ph, fill: paper, margin: 0pt, header: none, footer: none)
  set text(font: serif, fill: ink, lang: opt(meta, "lang", "es"))
  // Marco doble con esquinas.
  place(top + left, dx: 6mm, dy: 6mm, rect(width: pw - 12mm, height: ph - 12mm, stroke: 1.1pt + ink))
  place(top + left, dx: 8.5mm, dy: 8.5mm, rect(width: pw - 17mm, height: ph - 17mm, stroke: 0.5pt + ink))
  for (dx, dy, fx, fy) in ((4mm, 4mm, false, false), (pw - 18mm, 4mm, true, false),
                            (4mm, ph - 18mm, false, true), (pw - 18mm, ph - 18mm, true, true)) {
    place(top + left, dx: dx, dy: dy, corner(flip-x: fx, flip-y: fy))
  }
  for (dx, dy) in ((8.5mm, 8.5mm), (pw - 11.5mm, 8.5mm), (8.5mm, ph - 11.5mm), (pw - 11.5mm, ph - 11.5mm)) {
    place(top + left, dx: dx, dy: dy, diamond(size: 3mm))
  }
  pad(x: 30mm, top: 24mm, bottom: 18mm, block(height: 100%, {
    set align(center)
    let kicker = meta.at("kicker", default: none)
    if kicker != none { spaced(size: 8.5pt, tracking: 0.3em, kicker) }
    let img = meta.at("cover_image", default: none)
    if img != none and img != "" { v(0.35fr); block(height: 53mm, image(img, height: 53mm)); v(11mm) } else { v(1fr) }
    // Como en los originales: la última línea del título algo mayor que las anteriores.
    let words = upper(meta.at("title", default: "Sin título")).split(" ")
    let (head, last) = if words.len() > 2 { (words.slice(0, -1).join(" "), words.last()) } else { (none, words.join(" ")) }
    block({
      set par(leading: 0.42em)
      set text(font: fell, tracking: 0.02em, hyphenate: false)
      if head != none { text(size: 40.5pt, head); linebreak() }
      text(size: 46.5pt, last)
    })
    let sub = meta.at("subtitle", default: none)
    if sub != none { v(14mm); text(style: "italic", size: 12.5pt, sub) }
    v(10mm)
    ornament-rule(width: 75%)
    let desc = meta.at("description", default: none)
    if desc != none { v(8mm); block(width: 78%, text(style: "italic", size: 11pt, desc)) }
    let author = meta.at("author", default: none)
    if author != none { v(8mm); spaced(size: 10pt, fill: ink, tracking: 0.2em, author) }
    let place-line = meta.at("place", default: none)
    if place-line != none { v(8mm); spaced(size: 10pt, fill: ink, tracking: 0.2em, place-line) }
    let ed = meta.at("edition", default: none)
    if ed != none { v(2mm); spaced(size: 8.5pt, tracking: 0.25em, ed) }
    v(1.4fr)
    let foot = meta.at("colophon_line", default: none)
    if foot != none { spaced(size: 8pt, tracking: 0.32em)[·#h(0.6em)#foot#h(0.6em)·] }
  }))
}

// ---------------------------------------------------------------- índice
#let toc(entries, meta) = {
  block(width: 100%, {
    set align(center)
    v(4mm)
    spaced(size: 9.5pt, fill: red, tracking: 0.3em, meta.at("toc_kicker", default: "Índice"))
    v(0.2em)
    text(size: 2.05em, weight: 500, meta.at("toc_title", default: "Registro de los capítulos"))
    v(0.1em)
    ornament-rule(width: 75%)
  })
  v(6mm)
  let dots = box(width: 1fr, inset: (right: 0.6em), repeat(gap: 0.18em, text(fill: rulec, size: 1.15em)[·]))
  for e in entries {
    let indent = if e.level > 1 { 1.6em } else { 0pt }
    let lab = text(fill: red, size: if e.level > 1 { 0.95em } else { 1.05em }, e.label)
    block(above: 0pt, below: if e.level > 1 { 1.2em } else { 1.25em }, grid(
      columns: (2.2em + indent, 1fr, 2em), column-gutter: 0.6em, align: (right + bottom, left + bottom, right + bottom),
      lab, [#text(size: if e.level > 1 { 0.95em } else { 1em }, e.title) #dots], text(size: 0.95em, str(e.page)),
    ))
  }
  let note = meta.at("toc_note", default: none)
  if note != none {
    v(4mm)
    callout("aviso", meta.at("toc_note_title", default: "Aviso al lector."), note)
  }
}

#let code-block(body) = block(width: 100%, fill: shade, inset: 10pt, radius: 0pt, stroke: 0.5pt + rulec,
  text(size: 0.92em, body))
