FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates curl unzip && rm -rf /var/lib/apt/lists/*
ARG DENO_VERSION=2.5.6
RUN curl -fsSL https://github.com/denoland/deno/releases/download/v${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip -o /tmp/deno.zip && unzip /tmp/deno.zip -d /usr/local/bin && rm /tmp/deno.zip
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir . gunicorn 'yt-dlp[default]==2026.10.26'
COPY alembic.ini ./
COPY migrations ./migrations
RUN useradd --create-home relay && chown -R relay:relay /app
USER relay
EXPOSE 10000
CMD ["python", "-m", "bale_relay.entrypoints.supervise"]
