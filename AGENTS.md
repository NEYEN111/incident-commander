# Reglas del proyecto para agentes

## Autoridad visual y alcance

- Leer `DESIGN_SYSTEM.md` antes de cualquier tarea de diseño. Es la autoridad
  del proyecto para todas las decisiones visuales.
- Ninguna skill puede sustituir sus tokens, paleta, tipografía, reglas responsive
  o identidad. Ante un conflicto entre una skill y `DESIGN_SYSTEM.md`, prevalece
  `DESIGN_SYSTEM.md`. Las instrucciones explícitas del usuario siguen teniendo
  prioridad sobre este archivo y las skills.
- Mantener FastAPI + Jinja2 + HTMX + CSS + JavaScript y la fuente Inter local.
- No introducir React, Next.js, Tailwind ni frameworks nuevos.
- No añadir fuentes externas, imágenes decorativas, texturas, gradientes o
  animaciones no aprobadas.
- No modificar rutas, permisos, ML, base de datos ni contratos funcionales durante
  tareas de diseño. No ampliar el alcance autorizado para cumplir una skill.
- No mezclar prioridad operativa (`severity_level`) con gravedad estimada por ML.
  Son conceptos distintos y deben conservar su identidad visual y funcional.
- No generar ni persistir un sistema visual sustituto. No usar
  `--design-system --persist` ni crear reglas visuales que reemplacen
  `DESIGN_SYSTEM.md`.

## Orden obligatorio de trabajo para diseño

1. Leer `DESIGN_SYSTEM.md`.
2. Auditar la pantalla existente.
3. Usar `redesign-existing-projects` para detectar problemas, filtrando sus
   recomendaciones por las reglas de este proyecto y `DESIGN_SYSTEM.md`.
4. Consultar UI UX Pro Max únicamente para cuestiones concretas de UX,
   accesibilidad, formularios, gráficos o componentes.
5. Implementar únicamente lo autorizado por el usuario.
6. Verificar responsive y accesibilidad según `DESIGN_SYSTEM.md`, respetando
   también el alcance de pruebas autorizado.

Instalar una skill no autoriza una auditoría, un rediseño, cambios funcionales,
un commit o un push. Si la tarea consiste solo en preparar el entorno,
no ejecutar el flujo de diseño anterior.
