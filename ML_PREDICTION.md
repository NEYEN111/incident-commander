# Predicción de gravedad

`POST /api/predict` recibe JSON con exactamente los siguientes campos obligatorios.
Todos deben ser enteros JSON: no se convierten cadenas, decimales ni booleanos.
Los campos adicionales y los valores nulos se rechazan con HTTP 422.

| Campo | Valores admitidos |
| --- | --- |
| `day_of_week` | 1–7 (1 = domingo; 7 = sábado) |
| `hour` | 0–23 |
| `road_type` | 1, 2, 3, 6, 7, 9 |
| `speed_limit` | 20, 30, 40, 50, 60, 70, en **mph** |
| `urban_or_rural_area` | 1, 2, 3 |
| `light_conditions` | -1, 1, 4, 5, 6, 7 |
| `weather_conditions` | 1–9 |
| `road_surface_conditions` | -1, 1, 2, 3, 4, 5, 9 |
| `number_of_vehicles` | 1–17 |
| `junction_detail` | -1, 0, 13, 16, 17, 18, 19, 99 |
| `first_road_class` | -1, 1, 2, 3, 4, 5, 6 |

Las categorías reflejan el Pipeline STATS19 **2025** guardado. Los códigos `-1`
de datos ausentes y los códigos de categoría desconocida se entregan sin cambios
al preprocesamiento del modelo. `junction_detail` usa los códigos de 2025, que
difieren de la clasificación clásica de STATS19. La velocidad se restringe a los
seis valores observados durante el entrenamiento y el número de vehículos a
su rango observado de 1 a 17. Otros valores se rechazan con HTTP 422 para evitar
inferencias fuera de ese dominio; estos límites no garantizan la precisión del modelo.

El endpoint requiere una sesión autenticada con cualquier rol existente.
Conserva la autenticación y la protección CSRF del proyecto: una sesión ausente
redirige a `/login` (HTTP 303), una contraseña pendiente de cambio redirige a
`/account/password` y un Origin externo no permitido devuelve HTTP 403.

Ejemplo de petición:

```json
{
  "day_of_week": 2,
  "hour": 14,
  "road_type": 6,
  "speed_limit": 30,
  "urban_or_rural_area": 1,
  "light_conditions": 1,
  "weather_conditions": 1,
  "road_surface_conditions": 1,
  "number_of_vehicles": 2,
  "junction_detail": 0,
  "first_road_class": 3
}
```

La respuesta HTTP 200 contiene `prediction` (`Fatal`, `Grave` o `Leve`),
`probabilities` con esas tres claves y valores entre 0 y 1, y `model_version`
leído de la metadata (actualmente `1.0`). Las probabilidades proceden directamente
de `Pipeline.predict_proba`, asociadas al orden de `Pipeline.classes_`.

El servicio carga el joblib de `models/` en la primera petición válida y conserva
el Pipeline completo en memoria, una vez por proceso, incluso con primeras
peticiones concurrentes. No entrena ni modifica los artefactos. Las columnas del
DataFrame se ordenan como `feature_names_in_` del Pipeline; la metadata enumera
las mismas variables en un orden diferente. La falta de archivos o una carga
incompatible devuelve HTTP 503 y registra el error en el servidor.

Dependencias fijadas: scikit-learn 1.6.1 y joblib 1.6.0. Pandas proporciona el
DataFrame con nombres que requiere el ColumnTransformer. Los artefactos deben
permanecer en `models/` junto al directorio `app/` al desplegar; el Dockerfile
actual incluye ambos mediante `COPY . .`.
