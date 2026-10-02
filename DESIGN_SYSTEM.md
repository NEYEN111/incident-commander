# Sistema de diseño · Gestión de accidentes viales

**Estado:** propuesta previa a implementación. **Rama:** `feature/visual-redesign`.
**Base revisada:** `1bc5ceb083e6bfb217cb729d7c70f43b2bf1111c`.

Este documento define la dirección visual; no cambia pantallas, rutas, permisos,
contratos, datos ni comportamiento. Los tokens son propuestas, no CSS aplicado.
Stack: **FastAPI + Jinja2 + HTMX + CSS + JavaScript**. Mantener las dependencias
locales y el modelo ML existente, sin introducir un framework para rediseñar.

## 1. Dirección e identidad

Una herramienta de trabajo sobria para registrar, localizar y analizar accidentes.
La inteligencia del sistema se expresa mediante información comprensible,
probabilidades visibles y trazabilidad; no mediante efectos visuales futuristas.
Mantener el nombre **Sistema de Gestión de Accidentes Viales**, presentado con una
jerarquía legible y salto de línea natural en la navegación.

| Referencia | Principio que adoptamos | Aplicación propia |
| --- | --- | --- |
| Apple | Claridad, jerarquía, superficies contenidas | Lectura limpia, pocos niveles de énfasis, controles previsibles |
| Linear | Navegación eficiente y densidad cuidada | Menú estable, filas compactas y acciones contextualizadas |
| Stripe | Métricas legibles y comparación precisa | Números alineados, unidades, escalas y períodos explícitos |
| Notion | Organización del contenido y formularios | Secciones por significado, títulos descriptivos, edición ordenada |

No reproducir logos, pantallas, iconos propietarios ni composiciones reconocibles
literalmente. La identidad propia combina una paleta neutral, azul de interacción
y semántica vial constante. Evitar un dashboard compuesto exclusivamente por
mosaicos de tarjetas idénticas, grandes números sin contexto y gráficos ornamentales.

## 2. Diagnóstico de la interfaz actual

Revisión de `app/static/app.css`, `base.html`, login, índice/listado, detalle,
partials de campos viales y predicción, mapa, estadísticas, seguimiento y configuración.

- Tema oscuro predominante, fondos navy, acento naranja y sombras intensas.
- Inter local disponible; Fraunces se usa en marca, títulos y KPIs.
- Marca con punto que pulsa constantemente; algunos iconos de cronología son emojis.
- Sidebar por permisos y adaptación móvil mediante navegación horizontal que se envuelve.
- Registro completo dentro del listado; edición desplegable dentro del detalle.
- Filas con franja y etiqueta coloreadas según prioridad operativa, susceptibles de
  confundirse con la nueva clasificación ML si se reutiliza su apariencia.
- Detalle organizado en resumen, roles, cronología y seguimiento; sección ML real
  con versión, fecha, probabilidades e historial.
- Mapa Leaflet/OSM con clustering, filtros, contador y popup; Leve actualmente usa azul.
- Estadísticas con cuatro KPIs y diez bloques de barras HTML/CSS; cálculos en servicio.
- Muchos estilos locales/inline, tamaños compactos y énfasis visual poco uniforme.

**Conservar:** rutas y permisos, parciales Jinja2, contenido en español, etiquetas
STATS19, formularios nativos, cronología, historial ML, clustering, filtros y gráficos
ligeros. **Reemplazar en una fase posterior:** tema, tipografía de títulos, pulsación,
colores ambiguos, distribución del registro y estilos locales repetidos.

## 3. Tokens iniciales

Nombres propuestos para una futura capa de tokens. Migrar después las variables
actuales a estos roles; no limitar el cambio a invertir los colores del tema oscuro.

### 3.1 Colores

| Token | Valor | Uso |
| --- | --- | --- |
| `color-bg` | `#F5F6F8` | Fondo general gris muy claro |
| `color-surface` | `#FFFFFF` | Paneles, formularios y navegación |
| `color-surface-subtle` | `#F8FAFC` | Cabeceras y agrupaciones discretas |
| `color-hover` | `#EEF2F6` | Hover neutral de filas y navegación |
| `color-text` | `#171A1F` | Texto principal y títulos |
| `color-text-secondary` | `#5B6472` | Metadatos y ayudas |
| `color-text-muted` | `#667085` | Texto de menor jerarquía, aún legible |
| `color-border` | `#DDE2E8` | Separadores y contornos decorativos |
| `color-control-border` | `#7C8796` | Límites de controles identificables |
| `color-action` | `#175CD3` | Acción principal, enlaces y foco |
| `color-action-hover` | `#1849A9` | Hover de acción principal |
| `color-action-soft` | `#EFF4FF` | Selección o navegación activa |
| `color-on-action` | `#FFFFFF` | Texto sobre botón azul |
| `color-chart-neutral` | `#667085` | Magnitudes sin semántica de gravedad |
| `color-error` | `#B42318` | Error de formulario, siempre con explicación |
| `color-error-soft` | `#FEF3F2` | Fondo de error |
| `color-success` | `#067647` | Confirmación explícita de una operación |
| `color-success-soft` | `#ECFDF3` | Fondo de confirmación |
| `color-disabled-bg` | `#F2F4F7` | Control deshabilitado |
| `color-disabled-text` | `#667085` | Texto deshabilitado |

| Predicción ML | Color de texto/marcador/barra | Fondo suave | Lectura |
| --- | --- | --- | --- |
| Fatal | `#B42318` | `#FEF3F2` | Categoría estimada Fatal |
| Grave | `#9A4D00` | `#FFF4E5` | Categoría estimada Grave |
| Leve | `#0E7490` | `#ECFEFF` | Categoría estimada Leve; no indica seguridad |
| Sin predicción | `#475467` | `#F2F4F7` | Ausencia de resultado, no equivale a Leve |

Nombrar los pares como `color-ml-fatal`/`color-ml-fatal-soft`, etc. Mantenerlos
idénticos en detalle, historial, mapa y estadísticas. El azul queda principalmente
reservado a interacción; Leve usa cian, distinto del azul de acciones y del verde de success.
Errores y confirmaciones pueden compartir familias de color, pero su contexto,
texto e icono deben distinguirlos de las categorías ML.

### 3.2 Espaciado, radios y bordes

| Familia | Tokens/valores | Regla |
| --- | --- | --- |
| Espaciado | `space-0: 0`, `space-1: 4px`, `space-2: 8px`, `space-3: 12px`, `space-4: 16px`, `space-5: 20px`, `space-6: 24px`, `space-8: 32px`, `space-10: 40px`, `space-12: 48px`, `space-16: 64px` | Escala de 4 px; evitar valores arbitrarios |
| Radios | `radius-control: 8px`, `radius-panel: 12px`, `radius-small: 4px` | Controles y paneles moderados; no forma de cápsula por defecto |
| Bordes | `border-width: 1px`, `border-style: solid` | Separación habitual mediante borde, no sombra |
| Focus | `focus-width: 2px`, `focus-offset: 2px` | Contorno visible en todos los controles interactivos |

Separación entre etiqueta y campo: 8 px; entre campos: 16 px; entre grupos: 24–32 px.
Padding de panel: 24 px en escritorio y 16 px en móvil. Una superficie por sección
cuando haga falta; usar separadores internos antes que tarjetas anidadas.

### 3.3 Tipografía

`font-sans: "Inter", ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif`.
Usar `/static/fonts/inter.woff2`, ya disponible. No depender de fuentes externas.
Fraunces deja de ser identidad principal y no se usa en títulos, marca ni métricas.

| Token | Tamaño / interlineado | Peso | Uso |
| --- | --- | --- | --- |
| `text-caption` | 13 / 18 px | 400 | Metadatos secundarios; nunca instrucciones esenciales |
| `text-body` | 15 / 24 px | 400 | Texto general y etiquetas |
| `text-control` | 16 / 24 px | 400–500 | Campos y botones; evita zoom automático en móviles |
| `text-section` | 20 / 28 px | 600 | Títulos de sección |
| `text-page` | 28 / 36 px | 600 | Título de página en escritorio |
| `text-page-mobile` | 24 / 32 px | 600 | Título de página en móvil |
| `text-metric` | 32 / 40 px | 600 | Valor principal de KPI |

Números y porcentajes con `font-variant-numeric: tabular-nums`. Reservar monospace
para códigos técnicos donde ayude; no usarlo para correo, fecha o navegación.
No exagerar tamaños ni pesos. Ancho de lectura habitual: 65–75 caracteres.

### 3.4 Sombras y layout

| Token | Valor inicial | Uso |
| --- | --- | --- |
| `shadow-none` | `none` | Filas, KPIs y paneles habituales |
| `shadow-soft` | `0 1px 3px rgba(16,24,40,0.06)` | Elevación excepcional de un panel |
| `shadow-overlay` | `0 8px 24px rgba(16,24,40,0.10)` | Menú desplegable o drawer |
| `layout-sidebar` | `232px` | Navegación de escritorio |
| `layout-header` | `56px` mínimo | Cabecera compacta móvil/tablet |
| `layout-content-max` | `1200px` | Listado, detalle y estadísticas |
| `layout-form-max` | `880px` | Registro/edición |
| `layout-auth-max` | `400px` | Login |
| `layout-map-max` | `1600px` | Mapa, aprovecha el espacio disponible |
| `layout-gutter` | `32px / 24px / 16px` | Escritorio / tablet / móvil |
| `control-min-height` | `44px` | Inputs, selects y botones |
| `target-min-size` | `44 × 44px` | Área interactiva, incluidos iconos |

## 4. Arquitectura de navegación

Orden objetivo: **Resumen → Accidentes → Mapa → Estadísticas → Seguimiento**.
Administración se separa al final del menú; cuenta personal y cerrar sesión van
al pie. Un único destino activo, texto claro e iconos SVG locales opcionales.

| Destino | Situación actual | Decisión |
| --- | --- | --- |
| Resumen | No existe como pantalla independiente; `/` es listado + creación | Propuesta futura; no crear enlace vacío ni inventar métricas |
| Accidentes | `/`, detalle `/incidents/{id}` | Conservar rutas; entrada principal mientras no exista Resumen |
| Mapa | `/maps` | Acceso de primer nivel para todos los usuarios autenticados |
| Estadísticas | `/insights` | Conservar ruta; título de página «Análisis vial» |
| Seguimiento | `/follow-ups` | Conservar: tareas y responsables de accidentes sí aportan al trabajo |
| Administración | `/users`, `/groups`, `/settings` | Mostrar solo al administrador |
| Mi cuenta | `/account/password` | Mantener según permisos; acceso personal separado |

La página Resumen necesita aprobación de su ruta y de los datos que la alimentan.
No trasladar `/` ni añadir endpoints durante un cambio puramente visual. El menú
actual puede adoptar el estilo nuevo con sus destinos existentes primero.
Mantener permisos del servidor; ocultar acciones en pantalla no sustituye la autorización.

## 5. Componentes y estados comunes

- Cabecera de página: título, descripción breve cuando aporte contexto y una acción
  principal. Filtros debajo, sin competir con el título.
- Botón primario azul: guardar, registrar o calcular según contexto; secundarios
  blancos con borde. Acción destructiva con texto explícito y confirmación existente.
- Enlaces distinguibles por subrayado en contenido; navegación activa por fondo,
  peso y señal estructural, no solo color. Hover sin desplazamientos del layout.
- Filas para entidades; paneles para grupos de contenido. Etiquetas de estado cortas
  cuando sean útiles, sin transformar toda metadata en píldoras.
- Formularios con etiqueta persistente, unidad y ayuda cerca del campo. Placeholder
  no sustituye la etiqueta. Mantener campos desconocidos vacíos y «Sin datos» explícito.
- Estado vacío explica la ausencia; no muestra estadísticas ficticias. «Sin resultados
  con estos filtros» se distingue de «Todavía no hay accidentes».
- Carga localizada y breve: texto de progreso, control de doble envío y `aria-busy`
  en una implementación posterior. No sustituir permanentemente contenido por spinners.
- Confirmación de guardado discreta y textual; error visible, con causa y próximo paso.

## 6. Reglas por pantalla

### Login

Superficie blanca sobre fondo claro, ancho máximo 400 px, identidad y título sobrios.
Correo y contraseña apilados; acción de inicio de sesión a ancho completo. Conservar
SSO cuando esté configurado. Errores junto al formulario; nunca ornamentación que
compita con el acceso. Permitir gestor de contraseñas y pegado. Sin ilustración hero,
foto de accidente, panel publicitario ni animación de marca.

### Resumen/dashboard — diseño futuro

Resumen de trabajo, no portada promocional: título, período explícito, cuatro KPIs
ya definidos en análisis vial y accesos directos a Accidentes, Mapa y Estadísticas.
Un extracto de actividad o accidentes recientes solo si existen datos servidos.
No inventar tendencias, comparativas, indicadores de riesgo ni conteos globales a
partir del subconjunto del listado. Reutilizar el servicio de análisis si se aprueba
esta pantalla; no recalcular sus métricas en Jinja2. No añadir mapa duplicado por decoración.

### Lista de accidentes

Cabecera con «Registrar accidente» para usuarios gestores. Propuesta posterior:
presentar el registro como bloque desplegable separado del listado, conservando
el POST y sin requerir una ruta nueva. Filas blancas separadas por líneas suaves,
con título/ID, fecha del accidente, hora, zona y estado de gestión. Prioridad operativa
con etiqueta completa y estilo neutral; sin una franja roja que parezca predicción ML.
Si se muestra ML en esta pantalla en el futuro, utilizar un campo separado con el
prefijo «ML» y solo cuando el backend entregue la última predicción; no consultar
por fila ni derivar su gravedad de `severity_level`.
Acciones de fila discretas; cierre no debe dominar. En móvil, filas apiladas con
la información esencial visible y metadatos secundarios en una segunda línea.

### Registro y edición

Compartir la misma organización de campos y los parciales existentes. Secciones:

1. Identificación y gestión: título, descripción, prioridad operativa y privacidad.
2. Fecha y ubicación: fecha del accidente, hora, latitud, longitud y zona.
3. Vía e intersección: tipo de vía, velocidad en mph, intersección y clase de vía.
4. Entorno: iluminación, meteorología y superficie.
5. Vehículos: número de vehículos y ayuda sobre compatibilidad ML.

Dos columnas en escritorio/tablet cuando los campos quepan con comodidad; una en
móvil. Etiquetas completas y sin truncar categorías largas. No cambiar los códigos
ni las reglas de `road_fields.py` por motivos visuales. No convertir datos opcionales
en obligatorios para guardar: los accidentes antiguos incompletos deben funcionar.
Indicar por separado los requisitos para predecir: 11 entradas derivadas de fecha,
hora y nueve campos; velocidad compatible 20/30/40/50/60/70 mph y vehículos 1–17.
El registro actual admite velocidades más amplias: explicarlo sin alterar su contrato.
Acciones al final, sin una barra fija que oculte campos al abrir el teclado móvil.

### Detalle del accidente

Cabecera con título, fecha del accidente, estado y «Prioridad operativa: …» explícito.
La fecha de registro administrativo sigue separada. Mantener organización existente
Resumen, Roles, Cronología y Seguimiento; al implementar accesibilidad, navegación
por teclado coherente en las pestañas. Datos viales en pares etiqueta/valor, sin
meter cada campo en una tarjeta. Edición contextual y reconocible.
En escritorio, sección ML junto o después de los datos relevantes según espacio;
en móvil, apilada antes de las acciones de edición. Cronología legible y compacta,
con fecha, autor y evento; sustituir emojis por texto o SVG local accesible.

### Predicción ML

Sección «Predicción de gravedad por ML» con resultado «Gravedad estimada: …».
Tres barras horizontales comparables con **escala fija 0–100 %**, etiquetas Fatal,
Grave y Leve y porcentajes reales con un decimal. No normalizar cada barra a su
máximo visual ni usar medidores que sugieran diagnóstico o certificación.

Versión, fecha/hora y últimas cinco predicciones en una lista o tabla compacta.
Conservar el historial, sus snapshots y el aviso de estimación existente. No
reinterpretar «gravedad registrada» como `severity_level`: este campo representa
prioridad operativa, no una etiqueta real de gravedad.

- Usar «probabilidades estimadas», nunca «confianza», «certeza» o «riesgo real».
- Mostrar «Sin predicción» de forma neutral; no equivale a probabilidad cero.
- Datos incompletos/incompatibles: explicar qué campos revisar; nunca rellenarlos.
- Mantener «Calcular predicción»/«Volver a calcular» según estado y permisos.
- Si se recalcula después de editar, el resultado anterior pertenece a su snapshot;
  no presentarlo como si se hubiera calculado automáticamente con los nuevos datos.
- No convertir Fatal en alerta parpadeante ni Leve en mensaje de que el accidente es seguro.
- Resultado ML y prioridad operativa tienen nombres, posiciones y estilos distintos;
  el primero usa la paleta ML, la segunda un tratamiento neutral con su nombre configurado.
  Conservar los valores y colores administrativos almacenados sin reasignarlos a ML.

### Mapa

Mapa protagonista, ancho amplio; controles discretos sobre una franja clara fuera
del área cartográfica para no cubrir puntos. Conservar Leaflet, OpenStreetMap,
atribución, clustering, zoom, filtros, contador y popups. Sin API key.

Leyenda de las cuatro categorías ML siempre disponible. Marcadores con etiqueta
textual en popup y diferenciación adicional por forma o símbolo local; borde blanco
y contorno oscuro para destacar sobre cartografía heterogénea. Los clusters muestran
conteo neutral, no una gravedad agregada ficticia.

Popup: identificación, fecha, hora, zona, última predicción y probabilidades reales;
«Ver accidente» como acción inequívoca. No introducir coordenadas artificiales,
heatmap, mapas 3D ni información meteorológica nueva. Altura orientativa de escritorio:
`clamp(420px, 70dvh, 900px)`; móvil: `60dvh` con mínimo de 320 px y fallback `vh`.
Controles de mapa con targets de 44 px. Permitir continuar desplazando la página;
no exigir gestos complejos para acceder al detalle de un accidente.

### Estadísticas

Conservar KPIs, filtros 30/90/Todo, `Incident.date`, distinción de registros sin fecha,
última predicción única y cálculos del servicio. Un bloque compacto para los cuatro
KPIs; sin iconos grandes ni flechas de crecimiento inventadas.

Agrupar el resto por sentido: predicción/completitud, contexto vial y evolución temporal.
Barras horizontales para categorías largas; días ordenados Domingo–Sábado y horas
00–23. Evolución cronológica diaria/mensual como ahora; una representación más
compacta posterior debe mantener intervalos con cero y datos ausentes diferenciados.
Mantener conteos y denominadores visibles; dar formato español a porcentajes.

Colores ML solo en Fatal/Grave/Leve. Magnitudes y categorías sin relación con gravedad
usan gris; no asignar rojo a «Rural» ni verde a «Seca». Barras de frecuencias pueden
usar escala relativa al máximo si se declara; porcentajes/probabilidades usan 0–100 %.
No comparar prioridad operativa con predicción. No usar gráficos 3D, donuts por
costumbre ni gráficos sin valores textuales accesibles.

### Seguimiento

Mantener tareas, responsable, vencimiento y enlace al accidente. Priorizar pendientes
mediante orden y texto, no reutilizando Grave/Fatal. Lista sobria; estados de tareas
se distinguen de categorías ML. La ausencia de tareas es un estado vacío normal.

### Configuración y administración

Separar cuenta personal de administración. Conservar Usuarios, Grupos, prioridades,
estados, roles, SMTP y SSO según permisos. Secciones con título, explicación y
formulario propio; una acción de guardado por sección. Secretos siguen ocultos y
las ayudas explican cómo conservarlos. Las tablas permiten leer nombre y acciones
sin ruido visual; color de prioridad configurable no se convierte en color ML.
No volver a mostrar módulos SRE ocultos por el hecho de rediseñar la navegación.

## 7. Responsive real

| Rango | Navegación | Contenido |
| --- | --- | --- |
| Móvil: <768 px | Cabecera compacta y botón «Menú»; drawer accesible futuro | Una columna, gutter 16 px, KPIs 1–2 columnas según anchura, formularios apilados |
| Tablet: 768–1023 px | Cabecera y menú desplegable/drawer, sin sidebar permanente | Gutter 24 px, dos columnas solo cuando sean legibles, mapa amplio |
| Escritorio: ≥1024 px | Sidebar de 232 px, sección activa clara | Gutter 32 px, max-width por tarea; cuatro KPIs si caben |

Drawer futuro: cierre con Escape y botón visible, foco inicial y retorno al botón
que lo abrió, fondo no interactivo y orden de tabulación controlado. No implementarlo
en esta fase documental. Evitar una fila móvil de seis destinos que se envuelva
sin jerarquía, como ocurre con la navegación actual.

- Verificar anchuras 320, 390, 768, 1024 y 1440 px, zoom 200 % y reflow a 400 %.
- No bloquear orientación ni fijar el ancho del contenido al viewport de escritorio.
- Formularios al 100 % disponible; fechas/categorías largas no fuerzan overflow.
- Tablas pueden tener scroll horizontal localizado con cabeceras y región accesibles;
  el resto de la página no debe desplazarse horizontalmente.
- En móvil, filtros del mapa agrupados en un desplegable accesible; mostrar resumen
  de filtros activos, botón Limpiar y contador incluso con el panel cerrado.
- Estadísticas en una columna; conservar etiquetas, cantidades y unidades. Si hace
  falta scroll en un gráfico largo, la región será identificable y usable con teclado.
- Detalle y popups sin truncar información esencial; permitir salto de línea.

## 8. Accesibilidad y estados

Objetivo **WCAG 2.2 AA**. Los valores propuestos deben validarse nuevamente en la
composición real; estos pares calculados sirven como punto de partida:

| Par | Contraste aproximado |
| --- | --- |
| Texto principal / blanco | 17.44:1 |
| Texto secundario / blanco | 5.98:1 |
| Texto muted / fondo general | 4.60:1 |
| Azul de acción / blanco | 5.99:1 |
| Borde de control / blanco | 3.64:1 |
| Fatal / fondo Fatal | 6.05:1 |
| Grave / fondo Grave | 5.62:1 |
| Leve / fondo Leve | 5.15:1 |
| Sin predicción / fondo neutral | 6.98:1 |

Texto normal ≥4.5:1, texto grande ≥3:1; foco y elementos gráficos/control esenciales
≥3:1 respecto de su entorno. `color-border` es decorativo y no basta por sí solo
para identificar un input; usar `color-control-border`. No colocar texto blanco
sobre fondos suaves ni bajar opacidad de textos importantes.

- **Focus:** `:focus-visible` con contorno azul sólido de 2 px y offset de 2 px;
  sobre botón azul, separación blanca antes del contorno. No eliminar outline sin reemplazo.
- **Hover:** cambio suave de superficie o subrayado; estado distinguible sin animación.
- **Pressed/selected:** color más oscuro o señal estructural; no mover elementos.
- **Disabled:** superficie gris, texto legible y atributo nativo `disabled` cuando
  corresponda; explicar el motivo fuera del control, no solo con tooltip inaccesible.
- **Error:** texto descriptivo próximo al campo, borde/indicador y `aria-invalid`;
  ayudas relacionadas mediante `aria-describedby`. Resumen enlazado si hay varios errores.
- **Tamaño:** targets 44 × 44 px como regla; iconos pueden ser pequeños dentro del target.
- **Color:** siempre acompañar con texto, símbolo o patrón. ML, estados y prioridades
  no se reconocen únicamente por rojo/ámbar/cian.
- **Semántica:** encabezados ordenados, landmarks, etiquetas de formulario,
  listas/tablas nativas y enlace para saltar al contenido.
- **Dinámica:** mensajes HTMX/fetch en regiones `aria-live` apropiadas; errores
  anunciados y foco mantenido después de actualizaciones parciales.
- **Movimiento:** solo transiciones de estado de 100–150 ms; respetar
  `prefers-reduced-motion`. Sin pulsación ni zoom animado imprescindible.
- **Iconos:** SVG locales de una familia consistente, 16–20 px, decorativos con
  `aria-hidden`; botones de icono con nombre accesible y texto/tooltip complementario.
- **Mapa:** los puntos deben permitir foco y abrir su popup con teclado. Conservar
  un acceso textual a Accidentes; no convertir el mapa en la única vía de lectura.

## 9. NO HACER

- No glassmorphism excesivo; preferir superficies opacas legibles.
- No gradientes genéricos ni fondos decorativos que simulen tecnología.
- No sombras fuertes por todas partes.
- No tarjetas dentro de tarjetas sin necesidad.
- No píldoras para todo.
- No animaciones constantes ni indicadores pulsantes de marca.
- No emojis como sistema de iconos.
- No utilizar color solo por decoración.
- No convertir la aplicación en una landing page.
- No introducir React, Next.js, Tailwind u otro framework solo por el rediseño.
- No fuentes o librerías desde CDN en producción.
- No un tema oscuro como dirección principal ni Fraunces como firma tipográfica.
- No mezclar prioridad operativa, estado de gestión y gravedad estimada ML.
- No inventar datos, fechas, coordenadas, tendencias o probabilidades para llenar espacio.
- No modificar validaciones, rutas o permisos de forma incidental al cambiar estilos.
- No añadir Open-Meteo, fotos, heatmap o una nueva funcionalidad bajo el rediseño.

## 10. Orden propuesto para la fase de implementación posterior

1. Aprobar tokens y ejemplos estáticos de Login, listado y detalle antes de extender
   el estilo. No instalar herramientas o skills por este documento.
2. Aplicar base clara, Inter y estados de componentes al layout compartido.
3. Reorganizar visualmente formularios y detalle conservando campos y contratos.
4. Unificar semántica ML en detalle, mapa y estadísticas; comprobar estados vacíos,
   errores, permisos y datos antiguos incompletos.
5. Ajustar navegación responsive, mapa y gráficos; verificar teclado y contrastes.
6. Evaluar Resumen como alcance separado si se aprueba ruta y provisión de datos.

Criterio de aceptación futuro: ningún cambio en resultados ML, snapshots, prioridad
operativa, filtros temporales ni datos originales; mismo flujo funcional, mejor
legibilidad y navegación. Documentar los fallos heredados de UI para distinguirlos
de regresiones. Este archivo no autoriza implementaciones, commit ni push por sí solo.
