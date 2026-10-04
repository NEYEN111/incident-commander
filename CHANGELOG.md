# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims to follow
[Semantic Versioning](https://semver.org/spec/v2.0.0.html) once it reaches 1.0.

## [Unreleased]

### Entrega académica — accidentes viales + ML
- Interfaz clara con Inter local, navegación y administración en español, priorizando laptop.
- Registro y edición vial, análisis ML con probabilidades e historial, estadísticas y mapa
  con filtros por última predicción. La prioridad operativa permanece separada de la gravedad ML.
- Datos DEMO sintéticos, persistentes y de carga manual idempotente; documentación del modelo
  existente sin reentrenamiento ni cambios de métricas.
- Pruebas portables Windows/Linux, cobertura del flujo integrado y verificaciones de permisos.
- Cierre: credenciales excluidas de Git e imagen Docker, documentación actualizada, registro
  plegable y última categoría ML visible en el listado. SSO se conserva como autenticación opcional.

## Histórico del proyecto upstream

### Added — Phase 1: Core platform & auth
- Self-hosted FastAPI + HTMX app, deployable via Docker Compose with Postgres.
- Local authentication (argon2) with a first-boot bootstrap admin whose generated password is printed to the logs.
- Group-based RBAC with three roles: Admin, Incident Commander, Read-only.
- Admin UI to manage users and groups; forced password change on first login.
- Record-only incident lifecycle: declare, list, view, and close incidents (severity SEV1–SEV3, public/private).
- Encrypted settings store (Fernet) and a settings page; secret values never rendered or logged.
- Dark "war room" UI where colour encodes incident severity.

### Notes (históricas, no describen el estado actual)
- Slack channels, Google Meet, Google SSO, and SMTP email invites are planned for later phases; connection fields exist but integrations are not yet wired.

[Unreleased]: https://github.com/giammbo/incident-commander/commits/main
