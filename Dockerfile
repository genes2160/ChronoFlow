# ── stage 1: build deps ──────────────────────────────
FROM python:3.12-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── stage 2: lean runtime ────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# ✅ NEW: install ffmpeg
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

# copy only the installed packages from builder
COPY --from=builder /install /usr/local

# copy app code
COPY . .

ARG API_PORT=8000
ENV API_PORT=${API_PORT}

ARG API_HOST=0.0.0.0
ENV API_HOST=${API_HOST}

ARG DEBUG=false
ENV DEBUG=${DEBUG}

EXPOSE ${API_PORT}

CMD ["python", "api_server.py"]