FROM python:3.12-slim-bookworm AS compiler
RUN apt-get update && apt-get install -y --no-install-recommends g++ nlohmann-json3-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /build
COPY core/main.cpp ./main.cpp
RUN g++ -std=c++17 -O2 -Wall -Wextra -Wpedantic main.cpp -o ensalamento-core

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_ENV=production CORE_BINARY=/app/core/ensalamento-core PORT=10000
RUN apt-get update && apt-get install -y --no-install-recommends libstdc++6 ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 appuser
COPY --from=compiler /build/ensalamento-core ./core/ensalamento-core
COPY server ./server
COPY web ./web
COPY scripts ./scripts
RUN chown -R appuser:appuser /app
USER appuser
EXPOSE 10000
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-10000} --workers 2 --threads 2 --timeout 60 'server.app:create_app()'"]
