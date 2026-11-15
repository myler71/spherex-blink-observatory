FROM python:3.11-slim

WORKDIR /app/frontend

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

COPY frontend /app/frontend

EXPOSE 4173
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl -fsS http://127.0.0.1:4173/explorer.html >/dev/null || exit 1
CMD ["python3", "-u", "-m", "http.server", "4173", "--bind", "0.0.0.0"]
