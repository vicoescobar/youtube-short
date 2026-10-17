# Étape 1 : Build du Frontend Vue 3
FROM node:22-alpine AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm install
COPY frontend ./
RUN npm run build

# Étape 2 : Runtime Python avec FFmpeg
FROM python:3.12-slim

# Installation de FFmpeg, curl et des polices système indispensables pour les sous-titres ASS
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    fontconfig \
    fonts-dejavu-core \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installation de uv pour installer les dépendances Python à vitesse maximale
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Copie des fichiers de dépendances
COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev || uv sync --no-dev

# Copie du code source et des poids de modèles
COPY src ./src
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Création des dossiers pour les volumes
RUN mkdir -p output temp

EXPOSE 8000

# Lancement de l'API FastAPI et du Dashboard
CMD ["/app/.venv/bin/uvicorn", "src.api:app", "--host", "0.0.0.0", "--port", "8000"]
