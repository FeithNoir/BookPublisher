# Formato de entrada

BookPublisher lee **Markdown** (CommonMark + extensiones), **texto plano** y **Word (.docx)**. La muestra `samples/guia-formato.md` usa todo lo que sigue.

## Metadatos

```yaml
---
title: Título del libro
subtitle: Subtítulo
author: Autor
kicker: Línea sobre el título (p. ej. colección)
description: Texto breve para la portada
edition: Primera edición · 2026
lang: es
---
```

Sin bloque YAML, una primera línea suelta se toma como título.

## Capítulos

* El nivel de capítulo es el `#` más alto que se repite (si el libro usa `##` para capítulos, también vale).
* `# Capítulo 3: El puerto` → etiqueta «Capítulo 3» + título «El puerto». `# Capítulo 3` a secas → solo etiqueta.
* `# Prólogo`, `# Epílogo: …`, `# Interludio`, `# Agradecimientos`, `# Colofón`… → capítulos sin número.
* A mano: `# Título {.unnumbered}` o `# Título {kicker="Libro primero"}`.

## Texto

* `*cursiva*`, `**negrita**`, `~~tachado~~`, `` `código` ``, `[texto]{.smallcaps}` (versalitas), enlaces.
* Notas: `texto[^1]` y `[^1]: la nota`.
* `*Pendiente de consultar: …*` o `[…]{.pendiente}` → marca roja de pendiente.
* Rayas de diálogo: `—Hola —dijo.` (si el texto trae `— Hola`, se pega la raya al exportar).
* Comillas rectas `"así"` → «así» en textos en español.

## Bloques

* Listas con `-` o `1.`; una entrada que empieza en negrita (`- **Torneos.** …`) usa el estilo de entrada del tema.
* Citas con `>`.
* Recuadros: `> [!NOTA] Título opcional` (también `CONSEJO`, `IMPORTANTE`, `ADVERTENCIA`, `AVISO`, `PRECAUCION` y sus equivalentes en inglés `NOTE`, `TIP`, `WARNING`, `CAUTION`).
* Código con ```` ``` ```` y lenguaje para resaltar.
* Tablas GFM con alineación (`:---`, `:---:`, `---:`).
* Imágenes `![pie](ruta.png)` relativas al .md.
* Separador de escena: `***` o `---`.

## Texto plano

Párrafos separados por línea en blanco; las líneas que parecen títulos de capítulo («Capítulo 1», «CAPÍTULO I») abren capítulo.

## Word

Se leen estilos de título (Título 1–3), negritas, cursivas, listas, tablas e imágenes.
