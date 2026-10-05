# Sistema de Gestión de Accidentes Viales

Aplicación web académica para registrar accidentes viales, estimar su gravedad con Machine
Learning, consultar estadísticas y localizarlos en un mapa.

> **Alcance y límites.** La aplicación estima una gravedad (Fatal / Grave / Leve) a partir del
> contexto vial. No determina culpabilidad, no sustituye una valoración profesional y no es un
> sistema certificado de diagnóstico o riesgo. Una predicción *Leve* **no** significa que un
> accidente sea seguro.

## Flujo principal

Registrar accidente → completar datos viales → **Analizar con ML** → se guarda la predicción
(probabilidades, versión del modelo y datos de entrada) → se ve en **Estadísticas** → se localiza en
**Mapa** si tiene coordenadas.

## Dos conceptos que no deben mezclarse

| Concepto | Valores | Qué es |
| --- | --- | --- |
| Prioridad operativa | `SEV1` / `SEV2` / `SEV3` | Decisión humana de gestión: a qué accidente atender antes. |
| Gravedad estimada | `Fatal` / `Grave` / `Leve` | Salida del modelo ML. No se deriva de la prioridad ni la determina. |

Se guardan en campos distintos, se muestran con identidad visual distinta y el mapa filtra por la
gravedad estimada, no por la prioridad.

## Funcionalidades

- Alta y edición de accidentes: fecha, hora, coordenadas y características viales (variables STATS19).
- Prioridad operativa, estado, responsables y seguimiento (tareas con responsable y plazo).
- Análisis ML con historial: cada análisis es una *instantánea* independiente.
- Estadísticas: datos registrados (distribuciones, línea temporal, calidad de datos) separados de
  la evaluación académica documentada del modelo.
- Mapa con Leaflet y OpenStreetMap, filtros por fecha, gravedad estimada y zona.
- Usuarios, grupos (roles: Administrador, Coordinador, Solo lectura) y configuración.

## Machine Learning

### Asistente IA (opcional)

La página `/assistant` permite seleccionar un accidente y preguntar por su análisis.
Consulta los once datos actuales con el mismo Random Forest, sin guardar predicciones
ni modificar el historial. DeepSeek vía Hive explica el resultado; no reemplaza al modelo ML.

Configura `HIVE_API_KEY` únicamente en el entorno del servidor. `HIVE_MODEL` utiliza
por defecto `deepseek-ai/deepseek-v4.1-flash` y `HIVE_BASE_URL` utiliza
`https://api-cdn.thehive.ai/api/v3`. Sin clave, el sistema arranca y ML sigue funcionando.
No incluyas credenciales reales en Git. Reinicia el servidor después de cambiar el entorno.

Se envían a DeepSeek vía Hive la pregunta, las once variables y el resultado de la inferencia;
no se envían automáticamente título, descripción, coordenadas ni prioridad de atención.
La conversación no se persiste: cada pregunta usa los datos actuales del accidente.
Las explicaciones pueden contener errores y no constituyen explicabilidad causal.

### Modelo de gravedad

- Modelo: `RandomForestClassifier` (150 árboles, `max_depth=16`, `min_samples_leaf=5`,
  `class_weight=balanced_subsample`, `random_state=42`) dentro de un `Pipeline` de scikit-learn 1.6.1.
- Datos: STATS19, colisiones viales 2025, Department for Transport (Reino Unido), 101 525 registros.
- 11 variables: `day_of_week`, `hour` (derivadas de fecha y hora), `road_type`, `speed_limit`,
  `urban_or_rural_area`, `light_conditions`, `weather_conditions`, `road_surface_conditions`,
  `number_of_vehicles`, `junction_detail`, `first_road_class`.
- Velocidades admitidas por el modelo: 20, 30, 40, 50, 60 y 70 mph. Otro valor se puede guardar en el
  accidente, pero el análisis ML se rechaza con un mensaje claro.

Métricas **documentadas** del notebook (test reservado, 20 305 filas; no se repitió la evaluación):

| Métrica | Valor |
| --- | --- |
| Accuracy | 0.5577 |
| F1 macro | 0.3663 |
| Balanced accuracy | 0.4618 |
| ROC-AUC macro OVR | 0.6259 |

**Limitaciones conocidas.** Fuerte desbalance de clases: *Fatal* es aproximadamente el 1,43 % del
conjunto. En test, *Fatal* tiene precision 0,05 y recall 0,42 (redondeados): muchos falsos positivos
y poca capacidad para distinguirla. Los datos son del Reino Unido; su aplicación a otro contexto
vial no está validada. Detalle y procedencia en [ML_PREDICTION.md](ML_PREDICTION.md),
[DEMO.md](DEMO.md) y `models/modelo_evaluacion.json`.

## Tecnología

FastAPI, Jinja2, HTMX, CSS y JavaScript sin paso de compilación, PostgreSQL 16 (SQLAlchemy 2 +
psycopg 3, migraciones con Alembic), scikit-learn, Leaflet. Decisiones visuales en
[DESIGN_SYSTEM.md](DESIGN_SYSTEM.md); reglas de trabajo en [AGENTS.md](AGENTS.md).

## Ejecutar

### Con Docker Compose

```bash
cp .env.example .env     # completa SESSION_SECRET y FERNET_KEYS (comandos en el propio archivo)
docker compose up --build
```

Abre <http://localhost:8000>. La contraseña del administrador inicial se imprime **una vez** en los
registros (`docker compose logs app | grep "Generated password"`); cámbiala al entrar.

### Sin Docker (PostgreSQL local)

```bash
uv sync                                   # Python 3.12
export DATABASE_URL="postgresql+psycopg://USUARIO:CLAVE@localhost:5432/BASE"
export SESSION_SECRET="$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')"
export FERNET_KEYS="$(uv run python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
export BASE_URL="http://localhost:8000" SESSION_HTTPS_ONLY=false
uv run alembic upgrade head
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

En PowerShell usa `$env:NOMBRE = "valor"` en lugar de `export`. `SESSION_HTTPS_ONLY=false` solo
es adecuado para HTTP local; en producción debe ser `true` detrás de HTTPS.

### Datos DEMO

Sintéticos y de carga explícita; ver [DEMO.md](DEMO.md).

## Pruebas y calidad

```bash
uv run pytest                 # por defecto levanta PostgreSQL con testcontainers (requiere Docker)
uv run ruff check .
uv run ruff format --check .
```

Las pruebas usan una PostgreSQL temporal en Docker, separada de la base de trabajo y de DEMO.
`tests/test_entrypoint.py` ejecuta `docker/entrypoint.sh` dentro de un contenedor y siempre
requiere Docker. La prueba `tests/test_accident_flow.py` recorre el flujo accidente → ML →
persistencia → estadísticas → mapa con el modelo real.

**Migraciones verificadas:** `alembic upgrade head` llega a `0020_incident_predictions`.
`alembic check` conserva drift del esquema upstream: nulabilidad de timestamps en tablas
heredadas (incluidos catálogos, roles y seguimiento) y estructura del índice/constraint de
`inbound_integrations.token`. No afecta las columnas viales ni `incident_predictions`.
No se modificaron migraciones históricas; esa conciliación queda como mantenimiento separado.

## Módulos heredados (SRE)

El proyecto parte de un gestor de incidentes de infraestructura (Apache-2.0,
`giammbo/incident-commander`). Se conservan en el backend, **ocultos en la interfaz vial** y sin
integrarse al flujo de accidentes: integraciones Slack / Google Meet / webhooks, catálogo de
sistemas y componentes, alertas entrantes (`/ingest`), automatizaciones y postmortems.
SSO OIDC se conserva como opción de autenticación: se configura en Administración y aparece
en Login cuando está habilitado; no pertenece a los módulos ocultos.
Siguen montados y cubiertos por pruebas; no se retiraron para no romper rutas, permisos ni pruebas.
Retirarlos exigiría revisar esas dependencias y es una decisión pendiente. El README original se
conserva en [docs/UPSTREAM_SRE_README.md](docs/UPSTREAM_SRE_README.md).

## Seguridad

Contraseñas con argon2, sesiones firmadas `SameSite=Lax`, protección CSRF por Origin/Referer,
secretos de configuración cifrados con Fernet. `.env` y `.env.demo` contienen credenciales locales:
no se versionan, no se incluyen en la imagen Docker y no deben compartirse. Ver [SECURITY.md](SECURITY.md).

## Licencia

Apache License 2.0; ver [LICENSE](LICENSE) y [NOTICE](NOTICE). Se conserva la atribución al proyecto
original.
