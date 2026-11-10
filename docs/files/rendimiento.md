# Rendimiento

Medido el 10 de noviembre de 2026 en la máquina de desarrollo (Intel Xeon, 8 núcleos, 15 GB de RAM, Linux, Python 3.13, typst-py 0.15.2, PyMuPDF 2.1). Se reproduce con:

```bash
python scripts/benchmark.py libro.md --theme novela --warm
```

`benchmark.py` exporta con una caché vacía («frío») y otra vez con la caché llena («caliente»), y muestrea cada 50 ms la memoria de todo el árbol de procesos.

## Libros largos

| Libro | Palabras | Tema | Páginas | Frío | Caliente | Memoria pico |
|---|---:|---|---:|---:|---:|---|
| Novela del autor (privada, no está en el repo) | 222 841 | Novela clásica (A5) | 683 | **1,86 s** | **0,18 s** | 94 MB principal + 1 026 MB en 4 procesos |
| *Don Quijote* completo (dominio público) | 379 305 | Novela clásica (A5) | 1 026 | 4,1 s | 0,2 s | 84 MB + ~700 MB |
| *Don Quijote* completo | 379 305 | Sencillo (6×9 in) | 1 114 | 3,0 s | — | — |
| *Don Quijote* completo | 379 305 | Manual técnico (A4) | 605 | 3,8 s | — | — |

Reparto de la novela en frío: preparar 0,11 s · maquetar 0,91 s · foliar 0,69 s · portada e índice 0,02 s · unir 0,13 s. Leer el Markdown: 0,25 s.

Procesos frente a memoria (misma novela):

| Procesos | Tiempo | Memoria pico total |
|---:|---:|---:|
| 4 | 1,87 s | 1 089 MB |
| 2 | 3,00 s | 627 MB |
| 1 | 5,72 s | 383 MB |

Por defecto se usan hasta 4 procesos, uno menos que los núcleos y nunca más de los que caben con ~300 MB libres cada uno (`BOOKPUBLISHER_WORKERS` o `--workers` lo fuerzan). Pasados 90 s sin exportar, los procesos se cierran y la memoria vuelve al sistema.

## Interacción

| Operación | Tiempo |
|---|---|
| Vista previa de un capítulo (primera vez) | 0,12–0,20 s (Códice, cuerpo entero en flujo continuo: 0,44 s) |
| Vista previa ya vista o ya exportada | ~0,01 s |
| Cancelar una exportación en curso | 0,03–0,08 s hasta que la UI la confirma |
| Abrir un Markdown de 380 000 palabras | 0,22 s |
| Importar el Manual de Arbitraje (19 páginas, 6 tablas) | 1,8–2,2 s (la detección de tablas es la mayor parte) |
| Importar el Libro del Grupo (30 páginas) | 1,6–2,0 s |
| Escribir un .docx | < 0,1 s |

## Registro de mejoras

1. **Composición monolítica → por capítulos en paralelo.** Una sola compilación Typst de la novela: 3,2 s y 536 MB, sin progreso posible. Troceada en 22 fragmentos sobre 4 procesos: 1,7–1,9 s, con progreso por capítulo, cancelable y con caché por capítulo (0,18 s al repetir).
2. **Relleno a página impar fuera de Typst.** Hacerlo con `pagebreak(to: "odd")` dentro de cada fragmento no convergía con los folios; ahora Python añade la página en blanco al unir (`Chunk.pad`). Además el último capítulo ya no deja una página en blanco al final.
3. **Fuentes del cuerpo elegidas también por velocidad.** Source Serif 4 hacía la justificación 2,3–3,5 veces más lenta que Libertinus, EB Garamond o Charis SIL (medido sobre 200 000 caracteres: 0,75 s frente a 0,28–0,33 s). Manual técnico pasó a PT Serif y Sencillo a Charis SIL: el *Quijote* entero bajó de 13,5 s a 3,8 s (Manual) y de 15,1 s a 3,0 s (Sencillo).
4. **`fork` → `forkserver`.** Con `fork`, los procesos de composición heredaban el socket del servidor y quedaban vivos al cerrarlo, ocupando el puerto. Con `forkserver` no heredan nada; el coste de arranque es el mismo en la práctica.
5. **Memoria ociosa.** Se probó reciclar procesos con `max_tasks_per_child`, pero en Python 3.13 bloqueaba el grupo; se sustituyó por cerrar el grupo tras 90 s sin uso.
6. **Vista previa con la caché de exportación.** La vista previa escribe en la misma caché que la exportación, así que revisar capítulos acelera la exportación posterior.
7. **Progreso por palabras.** Pesar la barra por palabras y no por capítulos evita que se quede quieta en un capítulo largo; los fragmentos más grandes se envían primero para repartir mejor la carga.
