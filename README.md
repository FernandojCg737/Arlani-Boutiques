# AtelierAranier — Entorno de desarrollo

Plataforma web y móvil para gestión de tiendas de ropa (SI2 — Examen 1).

## Estructura

```
PROYECTO/
├── backend/     FastAPI + SQLAlchemy + Alembic (Python 3.12)
├── frontend/    Angular 22 (standalone, SCSS)
├── mobile/      Flutter + Dart
├── docker-compose.yml
└── .env         Variables para Postgres (usadas por docker-compose)
```

## Requisitos

- Docker Desktop (con Docker Compose v2)
- Node.js 22+ y Flutter SDK solo si quieres correr frontend/mobile fuera de Docker

## Levantar backend + base de datos + frontend con Docker

```bash
docker compose up --build
```

Esto levanta:

| Servicio | URL                          | Descripción                     |
|----------|-------------------------------|----------------------------------|
| backend  | http://localhost:8000/docs   | FastAPI (Swagger UI)             |
| frontend | http://localhost:4200        | Angular (ng serve con recarga)   |
| db       | localhost:5433                | PostgreSQL 16 (host)             |
| adminer  | http://localhost:8080         | UI para inspeccionar la base     |

> **Puerto 5433, no 5432:** en esta máquina ya hay un PostgreSQL nativo instalado como servicio de Windows (`postgresql-x64-16`) ocupando el 5432, así que el contenedor se publica en 5433 para no chocar con él. Esto es solo el puerto visible desde Windows/pgAdmin/SQLTools — dentro de la red de Docker (backend → db) se sigue usando el 5432 normal, sin cambios.

Login de Adminer: sistema `PostgreSQL`, servidor `db`, usuario/clave/base según `.env`.
Login de pgAdmin / SQLTools: host `localhost`, puerto `5433`, usuario/clave/base según `.env`.

Para bajar todo: `docker compose down` (agrega `-v` si además quieres borrar los datos de Postgres).

## Backend sin Docker (opcional)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env   # y apuntar POSTGRES_HOST a localhost si Postgres corre aparte
uvicorn app.main:app --reload
```

### Pruebas (pytest)

Con el stack levantado (las de integracion usan la base local; el envio de correos se intercepta, no sale ninguno):

```bash
docker compose exec backend pip install -r requirements-dev.txt
docker compose exec backend pytest
```

### Migraciones (Alembic)

```bash
cd backend
alembic revision --autogenerate -m "descripcion"
alembic upgrade head
```

## Frontend sin Docker (opcional)

```bash
cd frontend
npm install
npm start
```

## Móvil (Flutter)

No corre en Docker (necesita emulador/dispositivo). Con el backend levantado (Docker o local):

```bash
cd mobile
flutter pub get
flutter run
```

La URL base de la API está en `mobile/lib/core/api_config.dart`:
- Emulador Android → `http://10.0.2.2:8000/api/v1` (ya configurado)
- iOS / desktop → `http://localhost:8000/api/v1`
- Dispositivo físico o producción → cambiar por la IP de red o la URL de Render una vez desplegado

## Notas

- **No usar** frameworks de e-commerce (PrestaShop, Shopify, Magento, WooCommerce) como implementación — están prohibidos por el enunciado, solo se investigan en la Parte I del documento.
- El despliegue final debe ser en la nube (Render), no en localhost — la imagen `frontend/Dockerfile` (build con nginx) y `backend/Dockerfile` ya están listas para ese despliegue.
- Variables sensibles (`SECRET_KEY`, credenciales de Postgres) están en `.env` / `backend/.env`, que **no se suben a git** (ver `.gitignore`). Antes de desplegar, cambiar `SECRET_KEY` y las contraseñas por defecto.
