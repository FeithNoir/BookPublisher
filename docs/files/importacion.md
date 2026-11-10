# Importación de PDF

`readers/pdf_reader.py` convierte un PDF con texto en el mismo modelo que el resto de lectores; de ahí salen el Markdown (con sus imágenes en `<nombre>-imagenes/`) y el Word.

## Qué hace

1. **Extraer** cada línea con sus fragmentos (fuente, tamaño, color, negrita/cursiva). Las ligaduras se expanden. En fuentes Type3 (las que generan Chrome y Skia) el estilo se lee del `FontDescriptor` (`FontWeight`, `ItalicAngle`), porque el nombre no lo dice.
2. **Quitar el mobiliario:** líneas del 10 % superior o inferior que se repiten en al menos el 30 % de las páginas (cabeceras y pies), números de página (arábigos y romanos) y restos de adornos.
3. **Portada e índice:** una primera página con poco texto y un tamaño muy grande se interpreta como portada (título, antetítulo, subtítulo, descripción, lugar, edición, imagen). Las páginas de índice se descartan —BookPublisher lo regenera— pero se conservan su título y su nota.
4. **Medir el cuerpo** (tamaño, márgenes, interlineado más frecuente) y **agrupar** líneas en párrafos: un salto mayor que 1,15 interlineados, una sangría o una última línea corta cierran el párrafo. Las capitulares se vuelven a unir a su palabra.
5. **Títulos:** se ordenan los tamaños mayores que el cuerpo; el nivel de capítulo es el de los títulos que llevan antetítulo («CAPÍTULO IV»).
6. **Unir entre líneas y páginas:** se juntan los párrafos partidos por un salto de página y se unen las palabras cortadas con guion (también U+2010, U+2011 y el guion blando) cuando la siguiente línea empieza en minúscula.
7. **Tablas:** `find_tables` de PyMuPDF solo en páginas con trazos suficientes; las celdas se rellenan con las líneas extraídas (conservan estilo y marcas) y las tablas consecutivas partidas entre páginas se unen.
8. **Imágenes:** se descartan fondos y adornos repetidos; las transparencias (SMask) se respetan; la imagen de portada se toma tal como se ve (recortes incluidos). El texto pequeño bajo una imagen se toma como pie.
9. **Marcas:** «†» y los textos en rojo que empiezan por «Pendiente de consultar» se conservan como marcas; las versalitas sintéticas de los navegadores («B» + «ucara» en pequeño) se reconstruyen como `[Bucara]{.smallcaps}`.

## Prueba con los PDF de Armagedón

Los dos PDF de referencia (no incluidos en el repositorio) se importan así:

| | Manual de Arbitraje | Libro del Grupo |
|---|---|---|
| Páginas | 19 | 30 |
| Capítulos | 14 (preámbulo, I–IX, anexos A–C, colofón) | 10 |
| Tablas | 6 | 1 |
| Imágenes | 1 + escudo de portada | 1 + escudo de portada |
| Palabras unidas | 54 | 143 |
| Tiempo | ~2 s | ~1,7 s |

Reexportados con el tema Códice dan 19 y 30 páginas, como los originales.

## Límites conocidos

* No hay OCR: el estudio rechaza con un mensaje claro un PDF escaneado sin capa de texto.
* Si el PDF original pierde texto entre páginas (pasa en los dos de referencia: Chrome recortó alguna línea al paginar), el importador no puede recuperarlo.
* Glifos mal codificados en el propio PDF (p. ej. la ligadura «fi» de la página 15 del Manual, que el PDF declara como «f») se importan tal cual.
* Diseños a varias columnas o con texto rodeando imágenes se leen en orden de lectura aproximado.
* Word no tiene notas al pie reales con python-docx: las notas van al final, en «Notas».
