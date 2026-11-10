// Tema «Manual técnico»: guías y manuales. Inter para títulos, PT Serif
// para el texto, JetBrains Mono para código; capítulos numerados en página
// nueva, secciones numeradas (1.1, 1.2), recuadros de nota/consejo/aviso,
// tablas rayadas e índice con secciones.
#import "../_lib/common.typ": *

#let ink = rgb("#111827")
#let muted = rgb("#6b7280")
#let accent = rgb("#4f46e5")
#let soft = rgb("#eef2ff")
#let line-c = rgb("#d1d5db")
#let sans = ("Inter", "DejaVu Sans")
#let serif = ("PT Serif", "Libertinus Serif")
#let mono = ("JetBrains Mono", "DejaVu Sans Mono")

#let kinds = (
  nota: (rgb("#2563eb"), rgb("#eff6ff"), "Nota"),
  consejo: (rgb("#059669"), rgb("#ecfdf5"), "Consejo"),
  importante: (rgb("#7c3aed"), rgb("#f5f3ff"), "Importante"),
  advertencia: (rgb("#d97706"), rgb("#fffbeb"), "Advertencia"),
  aviso: (rgb("#d97706"), rgb("#fffbeb"), "Aviso"),
  precaucion: (rgb("#dc2626"), rgb("#fef2f2"), "Precaución"),
)

#let setup(meta, front: false, body) = {
  let (pw, ph) = page-dims(meta, "a4")
  let size = opt(meta, "font_size", 10.5) * 1pt
  set page(
    width: pw, height: ph,
    margin: (top: 26mm, bottom: 24mm, inside: 24mm, outside: 22mm),
    header-ascent: 35%,
    header: context {
      if is-blank-page() or is-opening-page() or front { return }
      let ch = current-chapter()
      set text(font: sans, size: 7.5pt, fill: muted)
      grid(columns: (1fr, auto),
        if ch != none { ch.at("plain", default: "") } else { [] },
        meta.at("title", default: ""))
      v(-4pt)
      line(length: 100%, stroke: 0.4pt + line-c)
    },
    footer: context {
      if is-blank-page() { return }
      let n = counter(page).get().first()
      let lab = if front { numbering("i", n) } else { str(n) }
      set text(font: sans, size: 8pt, fill: muted)
      if calc.odd(here().page()) { align(right, lab) } else { align(left, lab) }
    },
  )
  set text(font: serif, size: size, fill: ink, lang: opt(meta, "lang", "es"),
    hyphenate: opt(meta, "hyphenate", true))
  set smartquote(quotes: bp-quotes(meta))
  set par(justify: true, leading: 0.68em, spacing: 1.05em, first-line-indent: 0pt,
    justification-limits: (spacing: (min: 85%, max: 130%)))
  set heading(numbering: (..n) => {
    let nums = n.pos()
    if nums.len() >= 2 { numbering("1.1", ..nums.slice(1)) }
  })
  show heading: it => {
    let lvl = it.level
    let sz = if lvl == 2 { 1.35em } else if lvl == 3 { 1.12em } else { 1em }
    block(above: if lvl == 2 { 1.9em } else { 1.5em }, below: 0.8em, sticky: true,
      text(font: sans, weight: if lvl == 4 { 600 } else { 700 }, size: sz, fill: ink, {
        context {
          let ch = current-chapter()
          let n = if ch != none { ch.at("number", default: none) } else { none }
          if n != none and lvl <= 3 {
            let c = counter(heading).get()
            text(fill: accent, str(n) + "." + c.slice(1).map(str).join(".") + " ")
          }
        }
        it.body
      }))
  }
  set list(marker: text(fill: accent)[•], indent: 0.4em, body-indent: 0.6em)
  set enum(indent: 0.4em)
  show raw.where(block: false): it => box(fill: rgb("#f3f4f6"), inset: (x: 2.5pt), outset: (y: 2.5pt), radius: 2pt,
    text(font: mono, size: 0.86em, it))
  show raw.where(block: true): set text(font: mono, size: 8.4pt)
  show link: set text(fill: accent)
  set footnote.entry(separator: line(length: 25%, stroke: 0.4pt + line-c))
  show footnote.entry: set text(size: 0.82em)
  show quote.where(block: true): it => block(inset: (left: 12pt, y: 4pt), stroke: (left: 2pt + line-c), text(fill: rgb("#374151"), it.body))
  body
}

#let chapter-opening(ch, meta) = {
  [#metadata(ch) <bp-chapter>]
  counter(heading).update(0)
  let label = ch.at("label", default: none)
  block(width: 100%, below: 2.2em, {
    v(10mm)
    let n = ch.at("number", default: none)
    if n != none {
      text(font: sans, size: 48pt, weight: 700, fill: accent, if n < 10 { "0" + str(n) } else { str(n) })
      v(-4mm)
    } else if label != none {
      text(font: sans, size: 9pt, weight: 600, fill: accent, tracking: 0.12em, upper(label))
      v(2mm)
    }
    if ch.at("title", default: none) != none {
      block(text(font: sans, size: 24pt, weight: 700, hyphenate: false, { set par(justify: false, leading: 0.45em); ch.title }))
    }
    v(3mm)
    line(length: 22%, stroke: 2.5pt + accent)
  })
}

#let first-paragraph(body, letter: none, rest: none, meta: (:)) = text(size: 1.06em, body)
#let span(cls, body) = if cls == "pendiente" { text(fill: rgb("#dc2626"), style: "italic", body) } else { body }
#let lead(body) = strong(body)

#let callout(kind, title, body) = {
  let (c, bg, name) = kinds.at(kind, default: kinds.nota)
  block(width: 100%, fill: bg, stroke: (left: 3pt + c), inset: (x: 12pt, y: 10pt), radius: (right: 3pt),
    above: 1.2em, below: 1.2em, {
      block(below: 0.6em, text(font: sans, size: 8.5pt, weight: 700, fill: c, tracking: 0.06em,
        upper(if title != none { title } else { name })))
      body
    })
}

#let code-block(body) = block(width: 100%, fill: rgb("#f6f8fa"), stroke: 0.5pt + rgb("#e5e7eb"), inset: 11pt, radius: 4pt,
  above: 1.1em, below: 1.2em, { set par(justify: false, leading: 0.6em); body })

#let table-block(header, rows, aligns) = {
  let n = header.len()
  let al = aligns.map(a => if a == "center" { center } else if a == "right" { right } else { left })
  set par(justify: false, leading: 0.55em)
  block(above: 1.2em, below: 1.3em, table(
    columns: if n > 1 { (auto,) * (n - 1) + (1fr,) } else { (1fr,) }, stroke: none, inset: (x: 7pt, y: 6pt),
    fill: (_, y) => if y == 0 { rgb("#111827") } else if calc.even(y) { rgb("#f9fafb") } else { none },
    align: (x, y) => al.at(x, default: left),
    table.header(..header.map(c => text(font: sans, size: 8pt, weight: 600, fill: white, c))),
    ..rows.flatten().map(c => text(size: 0.9em, c)),
    table.hline(stroke: 0.6pt + line-c),
  ))
}

#let figure-image(path, caption) = figure(image(path, width: 90%),
  caption: if caption == none { none } else { text(font: sans, size: 8pt, fill: muted, caption) },
  supplement: none, numbering: none)

#let scene-break() = block(above: 1.2em, below: 1.2em, line(length: 100%, stroke: 0.5pt + line-c))

#let cover(meta) = {
  let (pw, ph) = page-dims(meta, "a4")
  set page(width: pw, height: ph, margin: 0pt, header: none, footer: none)
  set text(font: sans, fill: white, lang: opt(meta, "lang", "es"))
  place(top + left, rect(width: 100%, height: 62%, fill: rgb("#111827")))
  place(top + left, dy: 62%, rect(width: 100%, height: 6pt, fill: accent))
  pad(x: 22mm, top: 30mm, {
    let k = meta.at("kicker", default: none)
    if k != none { text(size: 9pt, weight: 600, tracking: 0.15em, fill: rgb("#a5b4fc"), upper(k)); v(8mm) }
    block(width: 90%, text(size: 34pt, weight: 700, { set par(leading: 0.4em, justify: false); meta.at("title", default: "Sin título") }))
    let sub = meta.at("subtitle", default: none)
    if sub != none { v(6mm); block(width: 85%, text(size: 13pt, fill: rgb("#cbd5e1"), sub)) }
  })
  place(bottom + left, dx: 22mm, dy: -24mm, {
    set text(fill: ink)
    let au = meta.at("author", default: none)
    if au != none { text(size: 12pt, weight: 600, au); linebreak() }
    let ed = meta.at("edition", default: none)
    if ed != none { text(size: 9pt, fill: muted, ed) }
  })
}

#let toc(entries, meta) = {
  text(font: sans, size: 22pt, weight: 700, meta.at("toc_title_manual", default: "Contenido"))
  v(1mm)
  line(length: 22%, stroke: 2.5pt + accent)
  v(6mm)
  for e in entries {
    let l1 = e.level == 1
    block(above: if l1 { 0.9em } else { 0pt }, below: 0.55em, grid(
      columns: (if l1 { 1.6em } else { 1.6em + 1.2em }, 1fr, 2.4em),
      align: (left, left, right),
      if l1 { text(font: sans, weight: 700, fill: accent, e.label) } else { [] },
      [#text(font: if l1 { sans } else { serif }, weight: if l1 { 600 } else { 400 }, size: if l1 { 10pt } else { 9.5pt }, e.title) #box(width: 1fr, repeat(gap: 0.3em, text(fill: line-c)[.]))],
      text(font: sans, size: 9pt, fill: muted, str(e.page)),
    ))
  }
}
