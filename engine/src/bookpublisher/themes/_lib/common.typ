// Utilidades compartidas por todos los temas de BookPublisher.
// Los temas reciben `meta` (diccionario del front matter + opciones de la UI).

#let opt(meta, key, default) = {
  let o = meta.at("options", default: (:))
  let v = o.at(key, default: none)
  if v == none { meta.at(key, default: default) } else { v }
}

// Tamaños de página con nombre, en el orden en que aparecen en la UI.
#let page-sizes = (
  "a4": (210mm, 297mm),
  "a5": (148mm, 210mm),
  "carta": (8.5in, 11in),
  "6x9": (6in, 9in),
  "5.5x8.5": (5.5in, 8.5in),
  "b5": (176mm, 250mm),
)

#let page-dims(meta, default) = page-sizes.at(opt(meta, "page_size", default), default: page-sizes.at(default))

// ¿Esta página es la apertura de un capítulo o una página en blanco de relleno?
#let on-page(label-sel) = {
  let p = here().page()
  query(label-sel).any(m => m.location().page() == p)
}
#let is-blank-page() = on-page(<bp-blank>)
#let is-opening-page() = on-page(<bp-chapter>)

#let current-chapter() = {
  let p = here().page()
  // El capítulo vigente es el último cuya marca está en esta página o antes.
  let ms = query(<bp-chapter>).filter(m => m.location().page() <= p)
  if ms.len() > 0 { ms.last().value } else { none }
}

#let roman(n) = numbering("I", n)

// Relleno hasta página impar al final de un fragmento (capítulos en recto).
#let pad-to-recto() = context {
  if calc.odd(here().page()) {
    pagebreak()
    [#metadata("blank") <bp-blank>]
  }
}

// Marca de sección para el índice (la página es física dentro del fragmento).
#let section-mark(level, title) = context [#metadata((level: level, title: title, page: here().page())) <bp-section>]

#let image-or-none(path) = if path == none or path == "" { none } else { image(path) }

// Párrafo sin sangría de primera línea (tras títulos, separadores, tablas…).
#let bp-flush(body) = par(first-line-indent: 0pt, body)

// Comillas: en español, «angulares» y “inglesas” dentro (RAE). En otros idiomas, las de Typst.
#let bp-quotes(meta) = if opt(meta, "lang", "es") == "es" {
  (double: ("«", "»"), single: ("“", "”"))
} else { auto }
