FROM node:20.20.2-bookworm-slim AS frontend
WORKDIR /src
COPY jiuwenswarm/package*.json jiuwenswarm/
COPY jiuwenswarm/scripts jiuwenswarm/scripts
COPY jiuwenswarm/resources/agent jiuwenswarm/resources/agent
COPY jiuwenswarm/channels/web/frontend jiuwenswarm/channels/web/frontend
WORKDIR /src/jiuwenswarm/channels/web/frontend
RUN npm ci --no-audit --no-fund && npm run build:live-voice

FROM python:3.12-slim-bookworm
ARG SOURCE_COMMIT
LABEL org.opencontainers.image.revision=$SOURCE_COMMIT
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH" \
    JIUWENSWARM_DATA_DIR=/data JIUWENSWARM_CONFIG_DIR=/data/config \
    FRONTEND_HOST=0.0.0.0 FRONTEND_PORT=5173 \
    AGENT_SERVER_HOST=127.0.0.1 AGENT_SERVER_PORT=18092 \
    WEB_HOST=127.0.0.1 WEB_PORT=19000 GATEWAY_HOST=127.0.0.1 GATEWAY_PORT=19001
RUN apt-get update && apt-get install -y --no-install-recommends \
    git ca-certificates build-essential curl ffmpeg \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.12.1 \
    && useradd --uid 10001 --create-home --shell /bin/bash swarm
WORKDIR /app
COPY . .
COPY --from=frontend /src/jiuwenswarm/channels/web/frontend/dist jiuwenswarm/channels/web/frontend/dist
RUN uv sync --frozen --no-dev \
    && printf '%s\n' "$SOURCE_COMMIT" > /app/DEPLOYED_COMMIT \
    && mkdir -p /data /projects && chown swarm:swarm /data /projects
USER swarm
EXPOSE 5173
ENTRYPOINT ["/app/.venv/bin/python", "/app/deploy/live_voice/launch.py"]
