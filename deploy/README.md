# Deployment (not yet verified)

The Dockerfile and Render blueprint are prepared but have not been built or deployed.
This is still an experimental checkout. In particular, the download dependency lock,
real ffmpeg verification, file-ID cache reuse, polling lifecycle, shared search cache,
PostgreSQL concurrency and recovery tests remain acceptance gates.

Use one free web service and a persistent Neon PostgreSQL database with TLS. Do not
create a free Render database with expiry for durable bot state. Configure provider
keys as environment secrets and approve only no-charge models. No card or paid plan
should be added as part of this deployment.

`docker build -t bale-relay .` then `docker run --env-file .env -p 10000:10000 bale-relay`.
The supervisor migrates the database and starts HTTP, text and media processes.
There is intentionally no HTTP access log: webhook paths contain a secret.

Use a local administrative CLI connected to the same database to allow numeric Bale
user IDs. Register the HTTPS webhook only after checking /healthz and provisioning
users. Live API smoke tests require operator-provided credentials.

Free hosts may sleep or restart. `/status` requeues paused video work; unknown sends
are not retried automatically. Video processing is limited to an eight-minute pass,
60 minutes of source duration, 250 MB of source downloads, ten parts and 45 MB per
part. Completed parts are skipped after recovery. Local files are temporary.

Keep the text and media processes singletons in this prototype. Increasing process
counts is not supported until PostgreSQL contention and lane locking tests pass.
