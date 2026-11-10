// Tema «Novela clásica»: A5 de librería. Libertinus Serif, justificado con
// partición silábica en español, sangría de primera línea sin espacio entre
// párrafos, capitular en la apertura, folios centrados, cabeceras en versalitas
// (libro a la izquierda, capítulo a la derecha) y control de viudas y huérfanas.
#import "../_lib/common.typ": *
#import "../_lib/droplet/lib.typ": dropcap

#let ink = rgb("#1d1a16")
#let muted = rgb("#6d6559")
#let accent = rgb("#7a2e22")
#let serif = ("Libertinus Serif", "EB Garamond")

#let setup(meta, front: false, body) = {
  let (pw, ph) = page-dims(meta, "a5")
  let size = opt(meta, "font_size", 10.5) * 1pt
  let small = pw < 160mm
  set page(
    width: pw, height: ph,
    margin: if small { (inside: 19mm, outside: 15mm, top: 19mm, bottom: 21mm) }
            else { (inside: 25mm, outside: 20mm, top: 24mm, bottom: 26mm) },
    binding: left,
    header-ascent: 45%,
    footer-descent: 45%,
    header: context {
      if is-blank-page() or is-opening-page() or front { return }
      let p = here().page()
      let ch = current-chapter()
      let txt = if calc.even(p) { meta.at("author", default: none) } else { none }
      if txt == none and calc.even(p) { txt = meta.at("title", default: "") }
      if calc.odd(p) and ch != none { txt = ch.at("plain", default: "") }
      align(center, text(size: 0.78em, fill: muted, tracking: 0.12em, smallcaps(all: false, txt)))
    },
    footer: context {
      if is-blank-page() { return }
      let n = counter(page).get().first()
      align(center, text(size: 0.85em, fill: muted, if front { numbering("i", n) } else { str(n) }))
    },
  )
  set text(font: serif, size: size, fill: ink, lang: opt(meta, "lang", "es"),
    hyphenate: opt(meta, "hyphenate", true), number-type: "old-style",
    costs: (hyphenation: 90%, runt: 160%, widow: 400%, orphan: 400%))
  set smartquote(quotes: bp-quotes(meta))
  set par(justify: true, leading: 0.62em, spacing: 0.62em,
    first-line-indent: (amount: 1.3em, all: true), linebreaks: "optimized",
    justification-limits: (tracking: (min: -0.012em, max: 0.015em), spacing: (min: 80%, max: 135%)))
  show heading.where(level: 2): it => block(above: 1.6em, below: 0.9em, sticky: true,
    align(center, text(size: 1em, tracking: 0.08em, smallcaps(all: false, it.body))))
  show heading.where(level: 3): it => block(above: 1.3em, below: 0.7em, sticky: true, emph(it.body))
  show heading.where(level: 4): it => block(above: 1.1em, below: 0.6em, sticky: true, it.body)
  set footnote.entry(separator: line(length: 22%, stroke: 0.4pt + muted), indent: 0pt)
  show footnote.entry: set text(size: 0.8em)
  show quote.where(block: true): it => pad(x: 1.6em, block(above: 1em, below: 1em, text(size: 0.95em, it.body)))
  set list(indent: 1em, marker: [–])
  set enum(indent: 1em)
  show raw: set text(font: ("DejaVu Sans Mono",), size: 0.85em)
  show link: it => it
  body
}

#let chapter-opening(ch, meta) = {
  [#metadata(ch) <bp-chapter>]
  let has-title = ch.at("title", default: none) != none
  block(width: 100%, below: 2.4em, {
    set align(center)
    v(if has-title { 22% } else { 26% })
    let label = ch.at("label", default: none)
    if label != none {
      block(below: if has-title { 1.1em } else { 0.4em },
        text(size: 0.95em, tracking: 0.22em, fill: muted, upper(label)))
    }
    if has-title {
      block(below: 0.8em, text(size: 1.55em, hyphenate: false, style: "italic", ch.title))
    }
    text(fill: accent, size: 0.9em)[❦]
  })
}

#let first-paragraph(body, letter: none, rest: none, meta: (:)) = {
  if letter == none or not opt(meta, "dropcaps", true) {
    par(first-line-indent: 0pt, body)
  } else {
    dropcap(height: 3, gap: 3pt, fill: accent, font: serif, letter, rest)
  }
}

#let span(cls, body) = if cls == "pendiente" { text(fill: accent, style: "italic", body) } else { body }
#let lead(body) = smallcaps(body)

#let callout(kind, title, body) = pad(x: 1.2em, block(above: 1.2em, below: 1.2em, width: 100%,
  stroke: (top: 0.4pt + muted, bottom: 0.4pt + muted), inset: (y: 8pt), {
    if title != none { block(below: 0.5em, smallcaps(title)) }
    set text(size: 0.95em)
    body
  }))

#let table-block(header, rows, aligns) = {
  let n = header.len()
  let al = aligns.map(a => if a == "center" { center } else if a == "right" { right } else { left })
  block(above: 1.1em, below: 1.2em, text(size: 0.9em, table(
    columns: n, stroke: none, inset: (x: 5pt, y: 4pt),
    align: (x, y) => al.at(x, default: left),
    table.hline(stroke: 0.6pt),
    table.header(..header.map(c => smallcaps(c))),
    table.hline(stroke: 0.4pt),
    ..rows.flatten(),
    table.hline(stroke: 0.6pt),
  )))
}

#let figure-image(path, caption) = figure(image(path, width: 85%),
  caption: if caption == none { none } else { text(size: 0.85em, style: "italic", caption) },
  supplement: none, numbering: none)

#let scene-break() = block(above: 1em, below: 1em, width: 100%, align(center, text(fill: muted)[⁂]))

#let code-block(body) = pad(x: 1em, text(size: 0.85em, body))

#let cover(meta) = {
  let (pw, ph) = page-dims(meta, "a5")
  set page(width: pw, height: ph, margin: (x: 18mm, y: 22mm), header: none, footer: none, fill: rgb("#fbf8f1"))
  set text(font: serif, fill: ink, lang: opt(meta, "lang", "es"))
  set align(center)
  v(18%)
  let au = meta.at("author", default: none)
  if au != none { text(size: 11pt, tracking: 0.25em, upper(au)); v(10mm) }
  block(text(size: 26pt, hyphenate: false, { set par(leading: 0.4em, justify: false); meta.at("title", default: "Sin título") }))
  v(6mm)
  text(fill: accent, size: 14pt)[❦]
  let sub = meta.at("subtitle", default: none)
  if sub != none { v(6mm); text(size: 12pt, style: "italic", sub) }
  v(1fr)
  let ed = meta.at("edition", default: meta.at("place", default: none))
  if ed != none { text(size: 9pt, tracking: 0.15em, fill: muted, upper(ed)) }
}

#let toc(entries, meta) = {
  block(width: 100%, {
    v(12%)
    align(center, text(size: 1.05em, tracking: 0.25em, upper(meta.at("toc_title_novel", default: "Índice"))))
    v(2.2em)
  })
  set par(justify: false, first-line-indent: 0pt)
  for e in entries {
    block(above: 0pt, below: 0.85em, grid(
      columns: (1fr, auto), column-gutter: 0.4em,
      [#if e.label != "" and e.label != "—" and e.level == 1 [#text(fill: muted, size: 0.85em, e.label) #h(0.35em)]#e.title #box(width: 1fr, repeat(gap: 0.25em)[.])],
      align(right + bottom, str(e.page)),
    ))
  }
}
