---
title: Guía del formato de BookPublisher
subtitle: Cómo escribir en Markdown un libro, una novela o un manual que se exporte bien a PDF
author: Feith Noir
kicker: Documentación
edition: Edición de ejemplo · 2026
lang: es
---

# Primeros pasos

BookPublisher convierte un texto en **Markdown** (o texto plano, o Word) en un PDF maquetado con uno de sus temas. Esta guía es a la vez documentación y muestra: exportarla con el tema *Manual técnico* enseña casi todo lo que el motor sabe hacer.

## Qué es un capítulo

Cada título de primer nivel (`# Título`) abre un capítulo. Si el documento no usa `#` sino `##` para los capítulos, el lector lo detecta solo: toma como nivel de capítulo el más alto que se repita.

Los títulos con la forma `# Capítulo 3: El puerto` se separan en etiqueta («Capítulo 3») y título («El puerto»). Prólogo, Epílogo, Interludio y similares se tratan como capítulos sin número.

> [!NOTA] Capítulos sin número
> También puedes marcar un capítulo a mano con atributos: `# Agradecimientos {.unnumbered}`, o darle una etiqueta propia: `# El final {kicker="Libro tercero"}`.

## Metadatos del libro

Al principio del archivo puede ir un bloque YAML con los datos de la portada:

```yaml
---
title: El nombre del libro
subtitle: Una línea que lo explica
author: Quien lo escribe
edition: Primera edición · 2026
lang: es
---
```

Si no hay bloque y la primera línea del archivo es un título suelto, se usa como título del libro.

# Texto y estilo

## Énfasis y tipografía española

El texto admite *cursiva*, **negrita**, ~~tachado~~ y `código en línea`. Las comillas rectas se convierten en «comillas latinas» y el guion largo de diálogo se mantiene pegado a la palabra que sigue, para que nunca quede solo al final de una línea:

—¿Y si la raya cae justo al final del renglón? —preguntó alguien.

—No cae —respondió el motor—. Va unida a la palabra.

## Listas

Listas con viñetas:

- Un elemento corto.
- Otro elemento, algo más largo, para comprobar que la sangría francesa queda bien cuando la línea se parte en dos.
- Un tercero.

Y numeradas:

1. Escribe el texto.
2. Elige un tema.
3. Exporta y revisa.

## Notas al pie

Las notas se escriben con la sintaxis habitual[^1] y se colocan al pie de la página donde aparecen[^2].

[^1]: Es decir, una marca `[^1]` en el texto y su definición en cualquier otro lugar del archivo.
[^2]: En la exportación a Word van al final, en una sección «Notas», porque python-docx no sabe crear notas al pie reales.

# Bloques especiales

## Recuadros

> [!CONSEJO] Exporta pronto, exporta a menudo
> La vista previa compila solo el capítulo que estás mirando. Úsala sin miedo: tarda una fracción de segundo.

> [!ADVERTENCIA]
> Si un capítulo tiene un error de sintaxis, el aviso dice cuál y en qué línea, en lugar de fallar en silencio.

> [!IMPORTANTE] Privacidad
> Todo se procesa en tu máquina. Ningún texto sale de ella.

## Tablas

| Tema | Tamaño | Uso típico |
|:-----|:------:|-----------:|
| Códice | A4 | Reglamentos, libros de rol |
| Novela clásica | A5 | Narrativa larga |
| Manual técnico | A4 | Guías y documentación |
| Sencillo | 6×9 in | Cualquier texto |

## Código

```python
from bookpublisher.readers import read_any
from bookpublisher.render.pipeline import export_pdf, RenderOptions, Runtime

doc = read_any("mi-libro.md")
export_pdf(doc, RenderOptions(theme="novela"), "mi-libro.pdf", Runtime())
```

## Citas y separadores

> El buen tipógrafo es invisible: el lector no debe notar su trabajo, sino solo leer mejor.

Un separador de escena se escribe con tres asteriscos o una línea horizontal:

***

Y el texto continúa después, con la primera línea sin sangría.

# Exportar

## Rendimiento

El motor maqueta cada capítulo por separado y en paralelo, y guarda en caché los que no han cambiado. Un libro de mil páginas tarda unos pocos segundos; si solo tocas un capítulo, se recompone únicamente ese.

### Qué pasa al pulsar «Exportar»

1. **Preparar:** se lee el documento y se divide en capítulos.
2. **Maquetar:** cada capítulo se compone en su propio proceso.
3. **Foliar:** se recalculan los capítulos que no empiezan en la página 1, para que los números de página sean los reales.
4. **Portada e índice:** se componen con los números ya conocidos.
5. **Unir:** se juntan las piezas, se añaden marcadores y se guarda el PDF.

Puedes cancelar en cualquier momento; el progreso y el tiempo restante se actualizan con cada capítulo.
