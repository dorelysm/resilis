# Documento de requerimientos de Resilis

Documento en LaTeX, una sección por archivo.

```
Requerimientos/
  main.tex              documento principal (portada, índice, orden de secciones)
  secciones/            01_introduccion ... 10_pendientes
  figuras/              diagramas TikZ (arquitectura, flujo)
  ../referencias.bib    bibliografía compartida con el resto del proyecto
```

## Compilar

Requiere MiKTeX o TeX Live, con `latexmk` y `biber`.

```bash
cd Requerimientos
latexmk -pdf main.tex
```

Limpiar archivos auxiliares: `latexmk -c`.

## Notas

- Los requisitos llevan prioridad MoSCoW (M, S, C, W) y un criterio de aceptación mínimo.
- Las fórmulas de confianza y los pesos de las dimensiones son propuestas por validar (ver sección 10).
- Equipo, mentora, institución y fecha de la portada están en `main.tex`.
