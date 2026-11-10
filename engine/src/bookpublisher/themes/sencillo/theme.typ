// Tema «Sencillo»: limpio y legible para cualquier texto. Charis SIL a
// 11 pt en 6×9 pulgadas, títulos en Inter, sin adornos, folio centrado.
#import "../_lib/common.typ": *

#let ink = rgb("#1f2937")
#let muted = rgb("#6b7280")
#let serif = ("Charis SIL", "Libertinus Serif")
#let sans = ("Inter", "DejaVu Sans")

#let setup(meta, front: false, body) = {
  let (pw, ph) = page-dims(meta, "6x9")
  set page(width: pw, height: ph, margin: (inside: 20mm, outside: 17mm, top: 20mm, bottom: 22mm),
    footer: context {
      if is-blank-page() { return }
      let n = counter(page).get().first()
      align(center, text(font: sans, size: 8pt, fill: muted, if front { numbering("i", n) } else { str(n) }))
    })
  set text(font: serif, size: opt(meta, "font_size", 11) * 1pt, fill: ink, lang: opt(meta, "lang", "es"),
    hyphenate: opt(meta, "hyphenate", true))
  set smartquote(quotes: bp-quotes(meta))
  set par(justify: true, leading: 0.7em, spacing: 1.1em, first-line-indent: 0pt,
    justification-limits: (spacing: (min: 85%, max: 130%)))
  show heading: it => block(above: 1.6em, below: 0.7em, sticky: true,
    text(font: sans, weight: 600, size: if it.level == 2 { 1.2em } else { 1.05em }, it.body))
  show raw: set text(font: ("JetBrains Mono",), size: 0.85em)
  set list(indent: 0.5em)
  set enum(indent: 0.5em)
  show link: set text(fill: rgb("#2563eb"))
  body
}

#let chapter-opening(ch, meta) = {
  [#metadata(ch) <bp-chapter>]
  block(width: 100%, below: 1.6em, {
    v(16mm)
    let label = ch.at("label", default: none)
    if label != none { text(font: sans, size: 9pt, fill: muted, label); v(1mm) }
    if ch.at("title", default: none) != none {
      text(font: sans, size: 20pt, weight: 600, hyphenate: false, { set par(justify: false); ch.title })
    }
  })
}

#let first-paragraph(body, letter: none, rest: none, meta: (:)) = body
#let span(cls, body) = if cls == "pendiente" { text(fill: rgb("#b91c1c"), style: "italic", body) } else { body }
#let lead(body) = strong(body)
#let callout(kind, title, body) = block(width: 100%, fill: rgb("#f3f4f6"), inset: 10pt, radius: 3pt, {
  if title != none { block(below: 0.5em, text(font: sans, weight: 600, size: 0.9em, title)) }
  body
})
#let code-block(body) = block(width: 100%, fill: rgb("#f3f4f6"), inset: 9pt, radius: 3pt, { set par(justify: false); body })
#let table-block(header, rows, aligns) = {
  let al = aligns.map(a => if a == "center" { center } else if a == "right" { right } else { left })
  set par(justify: false)
  block(above: 1em, below: 1.2em, table(columns: header.len(), stroke: 0.5pt + rgb("#d1d5db"), inset: 6pt,
    align: (x, y) => al.at(x, default: left),
    table.header(..header.map(c => strong(c))), ..rows.flatten()))
}
#let figure-image(path, caption) = figure(image(path, width: 90%), caption: caption, supplement: none, numbering: none)
#let scene-break() = align(center, block(above: 1em, below: 1em, text(fill: muted)[\* \* \*]))

#let cover(meta) = {
  let (pw, ph) = page-dims(meta, "6x9")
  set page(width: pw, height: ph, margin: (x: 20mm, y: 26mm), header: none, footer: none)
  set text(font: sans, fill: ink, lang: opt(meta, "lang", "es"))
  v(25%)
  text(size: 26pt, weight: 700, { set par(leading: 0.4em); meta.at("title", default: "Sin título") })
  let sub = meta.at("subtitle", default: none)
  if sub != none { v(4mm); text(size: 12pt, fill: muted, sub) }
  v(1fr)
  let au = meta.at("author", default: none)
  if au != none { text(size: 11pt, weight: 600, au) }
}

#let toc(entries, meta) = {
  text(font: sans, size: 18pt, weight: 600, "Índice")
  v(6mm)
  for e in entries {
    block(below: 0.7em, grid(columns: (1fr, auto), column-gutter: 0.5em,
      [#if e.level > 1 { h(1.2em) }#e.title #box(width: 1fr, repeat(gap: 0.3em)[.])], str(e.page)))
  }
}
