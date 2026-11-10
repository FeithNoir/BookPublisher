# Temas

Un tema es una carpeta en `engine/src/bookpublisher/themes/<id>/` con:

* `theme.json`: nombre, descripción, colores de muestra y valores por defecto (`page_size`, `chapter_break` = `flow` | `page` | `recto`, `font_size`, `chapter_numbering` = `roman` | `arabic`, `toc_depth`, `dropcaps`, `paper`).
* `theme.typ`: funciones que el escritor Typst llama. Todas son obligatorias:

| Función | Para qué |
|---|---|
| `setup(meta, front: false, body)` | Página, márgenes, cabeceras y pies, fuentes, párrafos, títulos de sección, listas, notas. |
| `chapter-opening(ch, meta)` | Apertura de capítulo (`ch.label`, `ch.title`, `ch.number`, `ch.appendix`). Debe emitir `#metadata(ch) <bp-chapter>` para las cabeceras. |
| `first-paragraph(body, letter:, rest:, meta:)` | Primer párrafo (capitular si `letter` no es `none`). |
| `span(cls, body)` | Spans con clase (`pendiente`, …). |
| `lead(body)` | Entrada en negrita al inicio de un ítem («**Torneos.** …»). |
| `callout(kind, title, body)` | Recuadros `nota`, `consejo`, `importante`, `advertencia`, `aviso`, `precaucion`. |
| `table-block(header, rows, aligns)` | Tablas. |
| `figure-image(path, caption)` | Imágenes. |
| `scene-break()` | Separador (`***`). |
| `code-block(body)` | Bloques de código (recibe un `raw`). |
| `cover(meta)` | Portada. |
| `toc(entries, meta)` | Índice (`level`, `label`, `title`, `page`). |

`_lib/common.typ` ofrece `opt`, tamaños de página (`a4`, `a5`, `b5`, `carta`, `6x9`, `5.5x8.5`), `current-chapter()`, `is-opening-page()`, `is-blank-page()`, `section-mark`, `bp-flush` y `bp-quotes` (comillas «» en español).

## Códice

El estilo del *Manual de Arbitraje* y del *Libro del Grupo Armagedón*, calibrado midiendo los originales (posiciones de línea con PyMuPDF):

* A4, papel `#f1e7d0`, tinta `#2e2418`, rojo `#8c2f1b`; márgenes laterales de 75 pt.
* EB Garamond 12,4 pt con interlineado de 20,75 pt y 30,7 pt entre párrafos; IM FELL English para títulos, portada y capitulares.
* Cabecera «· TÍTULO ·» en versalitas espaciadas de 8,5 pt; folio centrado.
* Apertura de capítulo: etiqueta roja espaciada («CAPÍTULO IV», «PREÁMBULO», «ANEXO B») en romanos, título IM Fell de 23,2 pt y filete con rombo rojo; capitular roja de dos líneas.
* Secciones con ◆ rojo; tablas con cabecera en versalitas; «†» y «*Pendiente de consultar…*» en rojo (el segundo con subrayado punteado); recuadro «Aviso».
* Capítulos seguidos (flujo continuo); anexos y colofón abren página, como en los originales.
* Portada con doble marco, escudo, título en IM Fell (la última línea mayor), filete y datos de edición; índice «Registro de…» con etiquetas rojas y puntos guía.

## Novela clásica

A5, Libertinus Serif 10,5 pt justificado con partición silábica y límites de justificación, sangría de primera línea sin espacio entre párrafos, viudas y huérfanas penalizadas, capítulos en página impar con hundimiento, ❦ y capitular de tres líneas, cabeceras en versalitas (título del libro a la izquierda, capítulo a la derecha), separadores ⁂, portada sobria e índice con puntos.

## Manual técnico

A4, títulos en Inter, texto en PT Serif, código en JetBrains Mono con resaltado, capítulos con número grande índigo en página nueva, secciones numeradas (2.1, 2.1.1), recuadros de colores por tipo, tablas rayadas con cabecera oscura, índice con secciones (profundidad 2), cabecera con capítulo y título.

## Sencillo

6×9 pulgadas, Charis SIL 11 pt, títulos en Inter, sin adornos, folio centrado. Para cuando solo importa leer.

## Crear un tema

Copia `themes/sencillo`, cambia `theme.json` y ajusta `theme.typ`. Usa solo fuentes de `engine/src/bookpublisher/fonts/` (añade las nuevas con su licencia en `fonts/licenses/`). Los temas se cargan al arrancar; cualquier cambio en un `.typ` invalida la caché automáticamente.
