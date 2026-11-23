FROM node:24-bookworm-slim AS frontend
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.11-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 orbit
COPY server ./server
COPY --from=frontend /app/dist ./dist
RUN mkdir -p /app/server/data/imports && chown -R orbit:orbit /app
USER orbit
ENV ORBIT_DATA_DIR=/app/server/data ORBIT_DATABASE_PATH=/app/server/data/orbit.sqlite3
EXPOSE 8787
CMD ["python", "server/app.py", "--host", "0.0.0.0", "--port", "8787"]
