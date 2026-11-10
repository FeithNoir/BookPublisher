# Arquitectura

BookPublisher es una aplicación **local**: un motor en Python que hace el trabajo pesado y un estudio web en Angular que lo maneja. Nada sale de la máquina: el servidor escucha solo en `127.0.0.1` y no llama a servicios externos.

```
┌──────────────────────────── navegador ────────────────────────────┐
│  Angular 22 (zoneless, signals)                                   │
│  StudioStore ─ fetch ─▶ /api/…      EventSource ◀─ SSE progreso    │
└───────────────────────────────────────────────────────────────────┘
                 │                                   ▲
┌────────────────▼─────────── FastAPI (uvicorn) ─────┴──────────────┐
│ documentos en memoria · JobManager (hilo por trabajo) · estáticos │
└───────┬───────────────────────────┬──────────────────────┬────────┘
   lectores                   pipeline de PDF          escritores
 md · txt · docx · pdf     (ProcessPool + caché)       md · docx · typst
        │                           │
        ▼                           ▼
   modelo Document  ─────▶  fragmentos Typst por capítulo ─▶ PyMuPDF une
```

## Piezas

| Carpeta | Qué hace |
|---|---|
| `engine/src/bookpublisher/model.py` | Modelo común: `Document` → `Chapter` → bloques (párrafo, título, lista, cita, recuadro, código, tabla, imagen, separador) → elementos en línea (cursiva, negrita, versalitas, notas…). Todo lector produce esto y todo escritor lo consume. |
| `readers/` | `markdown_reader` (markdown-it-py + front matter, notas, atributos), `text_reader`, `docx_reader` y `pdf_reader` (PyMuPDF). |
| `writers/` | `markdown_writer`, `docx_writer` (python-docx) y `typst_writer` (genera el código Typst que llama a las funciones del tema). |
| `render/pipeline.py` | Exportación a PDF por fragmentos, en paralelo, con caché, progreso y cancelación. |
| `render/preview.py` | Vista previa de un capítulo o de la portada, reutilizando la misma caché. |
| `themes/` | Un tema = `theme.typ` (funciones de maquetación) + `theme.json` (nombre, valores por defecto). `_lib/common.typ` tiene utilidades compartidas; `droplet` (MIT) va incluido para las capitulares. |
| `fonts/` | Fuentes OFL incluidas (EB Garamond, IM FELL English, Inter, PT Serif, Charis SIL, JetBrains Mono). Typst nunca usa fuentes del sistema: el resultado es igual en cualquier máquina. |
| `server/` | API FastAPI y gestor de trabajos. |
| `cli.py` | `bookpublisher serve | export | import | themes`. |
| `web/` | Estudio Angular. |

## Por qué este stack

**Typst para componer.** Necesitábamos tipografía de libro (partición silábica en español, justificación óptima tipo Knuth-Plass, control de viudas y huérfanas, capitulares, notas al pie, índices con números de página reales) y velocidad para novelas de 800 páginas. Alternativas valoradas:

* *Navegador (Chromium/Paged.js/WeasyPrint):* es lo que usó la revista, pero la paginación CSS de libros largos es lenta (minutos), consume mucha memoria y la justificación es voraz, línea a línea. Las propias referencias de Armagedón salieron de Chrome y muestran sus límites (líneas muy abiertas, texto cortado entre páginas).
* *LaTeX:* calidad excelente, pero instalación de cientos de MB, compilaciones lentas y mensajes de error ilegibles para el usuario.
* *ReportLab:* rápido, pero habría que reimplementar la composición de párrafos.

Typst (vía el paquete `typst` de PyPI, un binario Rust embebido, sin instalar nada aparte) compone una novela de 223 000 palabras en un solo hilo en ~3 s y da errores con línea y mensaje claros. Con el troceado por capítulos de abajo baja a < 2 s.

**PyMuPDF para leer y unir PDF.** Es el extractor más completo (fuentes, tamaños, colores, banderas de estilo, imágenes con su posición, detección de tablas) y une cientos de PDF y escribe marcadores en milisegundos. *Licencia:* PyMuPDF es AGPL-3.0 (o comercial de Artifex). El código de BookPublisher es MIT; quien redistribuya BookPublisher empaquetado junto con PyMuPDF debe cumplir la AGPL para ese conjunto. Para uso personal y local no hay ninguna obligación adicional.

**python-docx** para Word (leer y escribir), **markdown-it-py** (+ `mdit_py_plugins`) para Markdown con front matter, notas y atributos `{.clase}`.

**FastAPI + SSE** para el servidor: el progreso llega por *Server-Sent Events* (unidireccional, se reconecta solo con `Last-Event-ID`, sin WebSockets).

**Angular 22 zoneless con signals** en la web, por coherencia con Magazine Layout Studio (misma cabecera, carril izquierdo por secciones, lienzo gris, pie «Desarrollado por feithnoir», Inter) y porque los signals encajan con un estado que cambia muchas veces por segundo durante una exportación.

## Exportación a PDF: el pipeline

El problema de un libro largo no es solo la velocidad: es que el usuario no sabe si la aplicación se colgó. El pipeline está pensado para que el progreso sea **real** y para que repetir sea barato.

1. **Preparar.** Se normalizan títulos («Capítulo 3: El puerto» → etiqueta + título; Prólogo/Epílogo sin número), se pegan las rayas de diálogo y el documento se parte en **fragmentos**: uno por capítulo (temas de flujo continuo como Códice usan un solo fragmento para el cuerpo, porque sus capítulos no abren página).
2. **Maquetar.** Cada fragmento es un `.typ` independiente que importa el tema. Se compilan en un `ProcessPoolExecutor` (hasta 4 procesos; ~300 MB libres por proceso) empezando en la página 1. Cada proceso guarda las fuentes cargadas una sola vez. Con cada fragmento terminado se emite un evento con palabras hechas/total y una estimación del tiempo restante.
3. **Foliar.** Con el número de páginas de cada fragmento ya se sabe dónde empieza cada capítulo; los que no empiezan en la 1 se recomponen con su folio real (es una segunda pasada igual de paralela). Las páginas en blanco para abrir en impar las añade Python al unir, no Typst.
4. **Portada e índice.** Se componen con los números de página definitivos (Typst devuelve las marcas `<bp-chapter-page>` y `<bp-section>` con `query`).
5. **Unir.** PyMuPDF inserta los fragmentos, añade marcadores (un capítulo = un marcador), metadatos y guarda sin recomprimir.

**Caché por contenido.** La clave de cada fragmento es el hash de su código Typst + versión de los temas; el PDF y sus marcas se guardan en `~/.cache/bookpublisher/chunks` (o `BOOKPUBLISHER_CACHE`). Cambiar una coma del capítulo 12 recompone solo el capítulo 12 (y los folios de los siguientes si cambió su número de páginas). La vista previa usa las mismas entradas: lo que ya miraste no se vuelve a componer al exportar. La caché se poda por antigüedad al superar 800 MB.

**Cancelación.** Un `threading.Event` se comprueba entre fragmentos; además `kill_pool()` termina los procesos en curso, así que cancelar tarda decenas de milisegundos aunque un capítulo enorme esté a medias. El siguiente trabajo crea un grupo nuevo.

**Memoria.** El proceso principal se queda en ~90 MB. Cada proceso de Typst llega a 150–250 MB en un libro largo; si el grupo queda ocioso 90 s se cierra y devuelve la memoria. Los procesos se crean con `forkserver` (no `fork`): no heredan hilos ni el socket del servidor. Por eso cualquier script que use el motor debe proteger su punto de entrada con `if __name__ == "__main__":`.

**Errores.** Si Typst no puede componer un fragmento, el error dice qué capítulo, el mensaje de Typst y el diagnóstico completo (plegado en la UI), con un botón para ir a ese capítulo.

## Servidor

* `POST /api/documents` (archivo .md/.txt/.docx o texto pegado) → esquema con capítulos, palabras y tiempo estimado por tema.
* `POST /api/documents/{id}/preview?target=cover|N` → PNG de las primeras páginas del capítulo.
* `POST /api/exports` → trabajo; `GET /api/jobs/{id}/events` (SSE), `POST /api/jobs/{id}/cancel`, `GET /api/jobs/{id}/files/{pdf|docx|md}`.
* `POST /api/imports` (PDF) → trabajo que produce Markdown (zip si hay imágenes) y Word, y deja el documento abierto en el estudio.
* Los trabajos se ejecutan de uno en uno (el paralelismo está dentro de cada exportación). Los eventos nunca exponen rutas del servidor. Subidas limitadas a 200 MB; solo se aceptan extensiones conocidas; los PDF se comprueban por cabecera.

## Estudio web

* `core/studio.store.ts`: estado con signals (documento, tema, opciones, capítulo seleccionado, vista previa, exportación). Un `effect` relanza la vista previa con 220 ms de retardo y aborta la anterior (`AbortController`), así arrastrar opciones no encola trabajo. Las opciones se guardan en `localStorage`.
* El progreso se pondera por fases (maquetar 0–60 %, foliar 60–92 %, portada, unir) y por **palabras**, no por capítulos, para que un capítulo largo no congele la barra. El tiempo restante se recalcula con la velocidad observada; antes de empezar se usa la velocidad medida en exportaciones anteriores de ese tema (`rates.json`).
* Cada capítulo de la lista muestra su estado (pendiente, compuesto, desde caché) mientras se exporta.
* Teclado: ← → para pasar de capítulo, Esc para cancelar.
