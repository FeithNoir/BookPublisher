# Diseño

## Para quién y para qué

Para quien escribe libros largos —novelas, guías, manuales, reglamentos— y quiere un PDF bonito sin pelearse con un maquetador, y para quien tiene un PDF y necesita recuperar el texto editable. Los dos casos de uso:

1. **Importar:** PDF → Markdown y/o Word, conservando la estructura (títulos, párrafos, cursivas y negritas, versalitas, listas, tablas, notas, imágenes) y limpiando lo que sobra (cabeceras, pies, números de página, palabras partidas a final de línea).
2. **Exportar:** Markdown, texto plano o Word → PDF con un tema (y también a Word o Markdown).

## Principios

* **Nunca dejar al usuario a ciegas.** Toda operación de más de medio segundo muestra fase, barra, capítulos hechos y tiempo restante, y se puede cancelar. La estimación aparece *antes* de pulsar «Exportar».
* **Lo que se mira, se ve al instante.** La vista previa compone solo el capítulo seleccionado (0,1–0,4 s) en lugar del libro entero.
* **Repetir es gratis.** Volver a exportar tras un cambio pequeño reutiliza todo lo que no cambió.
* **Errores con nombre y apellido.** Qué capítulo, qué pasó y qué hacer; el detalle técnico, plegado.
* **El texto del autor no se toca.** Las únicas transformaciones automáticas son tipográficas y reversibles (rayas de diálogo pegadas, comillas «» en español, títulos «Capítulo N: …» separados en etiqueta y título) y se pueden desactivar.
* **Privado por defecto.** Todo es local; el servidor solo escucha en esta máquina.

## Estudio

Mismo lenguaje visual que Magazine Layout Studio: cabecera blanca con icono índigo, carril izquierdo con secciones (Documento, Tema, Opciones, Capítulos, Acciones), lienzo gris con las páginas como hojas con sombra, botones verde/gris/azul en Acciones y pie «Desarrollado por feithnoir».

* **Documento:** arrastrar o elegir un .md/.txt/.docx, o pegar texto. Tarjeta con título, palabras y capítulos.
* **Tema:** cuatro tarjetas con muestras de color y la descripción del tema elegido.
* **Opciones:** tamaño de página, cuerpo, cómo empiezan los capítulos (seguidos, página nueva, página impar), capitulares, partición de palabras, portada, índice, título y autor.
* **Capítulos:** lista navegable con palabras por capítulo y un punto de estado durante la exportación (ámbar pendiente, verde compuesto, azul desde caché).
* **Lienzo:** barra con capítulo actual, flechas, número de páginas del bloque y tiempo de la vista previa; las primeras páginas del capítulo.
* **Panel de exportación:** flotante abajo; fase, barra, porcentaje, bloques, tiempo transcurrido y restante, «Cancelar (Esc)». Al terminar: páginas, tamaño, tiempo, capítulos desde caché, «Descargar» y «Abrir en otra pestaña».
* **Importar PDF:** zona de arrastre, opciones (imágenes, tablas), progreso por página, cancelar; al terminar, cifras (páginas, capítulos, palabras, tablas, imágenes, guiones unidos), descargas de Markdown y Word, vista del Markdown y «Abrir en el estudio».

## Formato de entrada

Ver [formato-markdown.md](formato-markdown.md). La muestra `samples/guia-formato.md` documenta y demuestra todas las construcciones.
