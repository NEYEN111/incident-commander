# Demostración académica

Los datos DEMO son sintéticos: no describen accidentes reales. Están separados de
la base de trabajo. No se crean al arrancar la aplicación ni mediante migraciones.

## Entorno local preparado

- PostgreSQL 16: contenedor `incident-commander-demo-db`.
- Volumen persistente: `incident-commander-demo-data`.
- Puerto exclusivo local: `127.0.0.1:55433`; base `ic_demo`.
- `.env.demo` contiene las credenciales locales y está ignorado por Git. No copiarlo
  al control de versiones ni compartir sus valores. El usuario de acceso está en
  `IC_ADMIN_EMAIL` y su contraseña local en `DEMO_ADMIN_PASSWORD`.
- No cambia `.env` ni la configuración de la base habitual.

Desde la raíz del repositorio, PowerShell:

```powershell
docker start incident-commander-demo-db
.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env.demo --host 127.0.0.1 --port 8765
```

Abrir `http://127.0.0.1:8765/login`. Al detener el servidor, el volumen DEMO conserva
los registros. `docker stop incident-commander-demo-db` detiene solo este entorno.

## Carga manual y repetible

En una base DEMO con el esquema del proyecto ya migrado y un usuario gestor activo:

```powershell
# En el entorno local preparado, recuperar solo la URL DEMO sin mostrarla:
$demoLine = Get-Content .env.demo | Where-Object { $_.StartsWith('DEMO_DATABASE_URL=') }
$env:DEMO_DATABASE_URL = $demoLine.Substring('DEMO_DATABASE_URL='.Length)
.venv\Scripts\python.exe -B scripts\seed_demo.py --confirm-demo --actor-email demo@example.test
Remove-Item Env:DEMO_DATABASE_URL
```

Para otra base DEMO, definir explícitamente `DEMO_DATABASE_URL` en el entorno. El
script exige PostgreSQL, un nombre de base que contenga `demo`, confirmación explícita
y un actor autorizado existente. No usa `DATABASE_URL` ni carga `.env`. El nombre
de la base es una protección contra errores, no sustituye comprobar el destino.

### PowerShell y bash: migrar y cargar otra base DEMO

Usar una base DEMO separada y un usuario gestor existente. Los valores siguientes son
marcadores, no credenciales reales. Alembic usa `DATABASE_URL`; el seed usa
`DEMO_DATABASE_URL`. Ambos deben apuntar explícitamente a la misma base DEMO.
Estos comandos se ejecutan en una terminal dedicada a DEMO.

```powershell
$env:DEMO_DATABASE_URL = 'postgresql+psycopg://USUARIO:CLAVE@localhost:5432/mi_base_demo'
$env:DATABASE_URL = $env:DEMO_DATABASE_URL
.venv\Scripts\python.exe -m alembic upgrade head
# Si es una base nueva, iniciar primero la app con esta URL y completar el usuario gestor.
.venv\Scripts\python.exe -B scripts\seed_demo.py --confirm-demo --actor-email demo@example.test
Remove-Item Env:DEMO_DATABASE_URL, Env:DATABASE_URL
```

```bash
export DEMO_DATABASE_URL='postgresql+psycopg://USUARIO:CLAVE@localhost:5432/mi_base_demo'
export DATABASE_URL="$DEMO_DATABASE_URL"
.venv/bin/python -m alembic upgrade head
# Si es una base nueva, iniciar primero la app con esta URL y completar el usuario gestor.
.venv/bin/python -B scripts/seed_demo.py --confirm-demo --actor-email demo@example.test
unset DEMO_DATABASE_URL DATABASE_URL
```

En Linux/macOS, tras preparar `.env.demo` y `.venv`, el entorno persistente se inicia con:

```bash
docker start incident-commander-demo-db
.venv/bin/python -m uvicorn app.main:app --env-file .env.demo --host 127.0.0.1 --port 8765
```

La carga inicial genera 12 accidentes, 10 predicciones, 11 ubicaciones y 3 tareas.
Los registros añadidos manualmente durante la revisión no forman parte de esos conteos iniciales.

Se crean 12 accidentes marcados `[DEMO 01]` a `[DEMO 12]`, con fechas relativas al día
de la primera carga, horas, prioridades operativas y estados variados. Hay 10
análisis completos, 2 registros intencionalmente sin predicción y 1 sin coordenadas.
Se incluyen 3 tareas sintéticas de seguimiento. Las ubicaciones son sintéticas en
el entorno de Leeds; las categorías y mph conservan el contrato STATS19.

Las predicciones las calcula `create_prediction`, el mismo servicio utilizado por
la aplicación: probabilidades, versión e inputs quedan guardados como snapshots.
No se asignan clases objetivo ni se cambian resultados para obtener variedad.
La salida del script muestra la distribución realmente obtenida. La carga inicial
verificada produjo Leve: 6, Grave: 2 y Fatal: 2.

Una segunda ejecución no duplica accidentes, tareas ni predicciones. No sobrescribe
registros existentes; conserva las ediciones hechas durante la exposición y las
fechas iniciales. Si hay un fallo, la transacción completa se revierte. Un bloqueo
transaccional serializa ejecuciones simultáneas. No incluye una acción de borrado.

## Recorrido de exposición

1. Login y lista de Accidentes: distinguir `[DEMO]` de información real.
2. Registrar un nuevo accidente sintético con fecha, hora y coordenadas.
3. Abrirlo y completar Vía, Entorno y Accidente; seleccionar mph compatible.
4. Analizar con ML, leer la clase estimada y probabilidades; volver a analizar para
   mostrar historial. SEV1/SEV2/SEV3 siguen siendo prioridad operativa independiente.
5. Estadísticas: consultar Todo o el período adecuado y ver la última predicción.
6. Mapa: localizar su marcador, abrir popup y regresar al accidente.
7. Seguimiento: ver tareas, responsable y plazo; visitar administración básica.

## Evidencia académica del ML

La fuente local es `notebooks/ML_STATS19_Accidentes.ipynb`; no hay un script separado
de entrenamiento/evaluación. El notebook carga STATS19 de colisiones 2025 desde el
CSV del Department for Transport del Reino Unido y conserva 101525 registros.
La división es estratificada 80/20: entrenamiento 81220 y test 20305, semilla 42.

Random Forest usa 11 entradas: day_of_week, hour, road_type, speed_limit,
urban_or_rural_area, light_conditions, weather_conditions, road_surface_conditions,
number_of_vehicles, junction_detail y first_road_class. Predice Fatal/Grave/Leve;
no predice prioridad operativa. Día y hora se derivan automáticamente.

El notebook selecciona hiperparámetros por F1 macro con RandomizedSearchCV (8
candidatos, 3 folds sobre entrenamiento). Los parámetros finales coinciden con el
artefacto leído: 150 árboles, max_depth=16, min_samples_leaf=5,
class_weight=balanced_subsample, random_state=42.

Resultados finales en test conservados en la celda 42 (índice desde cero):

| Métrica | Valor guardado |
| --- | --- |
| Accuracy | 0.557744397931544 |
| F1 macro | 0.3662578552185292 |
| Balanced accuracy | 0.461836400323646 |
| ROC-AUC macro OVR | 0.6259265021023273 |

El reporte por clase conserva Fatal: precision 0.05, recall 0.42, F1 0.09 (291 casos);
Grave: 0.29/0.32/0.31 (5038); Leve: 0.79/0.64/0.71 (14976). Son valores redondeados
del reporte. El gráfico de matriz de confusión está guardado; no se inventan sus
cifras numéricas. Fatal representa aproximadamente 1.43 % del dataset, lo que
respalda la limitación por desbalance y los numerosos falsos positivos de esa clase.

`models/modelo_evaluacion.json` transcribe esa evidencia con hashes SHA-256 de las
fuentes y del artefacto actual. Un test verifica las métricas contra las salidas
guardadas. Estadísticas presenta estos resultados como evaluación documentada,
separada de los conteos y predicciones de la base DEMO. No se ha vuelto a entrenar
ni evaluar el artefacto: la coincidencia de parámetros no es una nueva evaluación.
