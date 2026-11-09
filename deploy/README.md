# Deployment and operations

The repository includes a [Dockerfile](../Dockerfile) and a
[Render blueprint](../render.yaml). Treat the first deployment as an experimental
pilot until the [acceptance checks](ACCEPTANCE.md) pass on the intended host.

## Prepare the environment

Use persistent PostgreSQL with TLS. SQLite is rejected when `APP_ENV=production`.
The Render blueprint expects an external database; verify the database service's
current persistence and expiry policy before relying on it.

Configure the variables in [Configuration](../docs/configuration.md), including
`APP_ENV=production`, `RECEIVER_MODE=webhook`, `DATABASE_URL`, `BALE_TOKEN` and
an independent `WEBHOOK_SECRET` of at least 32 characters. Add provider keys
separately; approve only models verified for the intended no-charge account.
The blueprint includes core variables, but optional provider keys and search
settings must also be supplied by the operator.

Keep credentials in host secrets or the ignored local `.env`. HTTP access logs
must stay disabled because webhook paths contain a secret. Confirm host plan
availability, limits and billing settings before provisioning resources.

## Start the container

From the repository root, using a production-configured environment file:

```powershell
docker build -t bale-relay .
docker run --env-file .env -p 10000:10000 bale-relay
```

The supervisor applies Alembic migrations and starts the HTTP server, text worker
and media worker as separate processes. It requires webhook mode. Keep one service
instance, one text worker and one media worker in this prototype; local contention
tests do not establish that a scaled deployment is safe.

The image includes ffmpeg, ffprobe, Deno and yt-dlp. Python direct dependencies come
from `requirements-runtime.txt`; transitive packages and system dependencies are
not fully locked.

## Approve users and register the webhook

1. Check the service's `/healthz` endpoint.
2. From a local CLI configured for the same production database, run
   `bale-relay allow-user YOUR_NUMERIC_ID`.
3. Register the public HTTPS origin:

```powershell
bale-relay set-webhook https://YOUR-SERVICE.onrender.com
bale-relay webhook-info
```

`webhook-info` reports only whether a webhook exists. Do not print or share the
full webhook URL. Registration and the receiver must use the same token and
webhook secret. To revoke access, run `bale-relay block-user YOUR_NUMERIC_ID`.

### Windows identity and registration helper

Before registering a new bot's webhook, stop any poller and run:

```powershell
.\deploy\bale-admin.ps1 -Action Identify
```

The helper requires no Python installation. It reads `BALE_TOKEN` from the local
`.env`, asks you to send a random marker in a private chat, and returns only the
matching private sender's numeric ID. It refuses to run when a webhook exists.
Use it during initial setup, before starting normal message reception.

If a Python CLI is unavailable, after the container has applied migrations you
can approve that ID through the database provider's SQL editor:

```sql
INSERT INTO bot_users (id, enabled, generation, model, mode)
VALUES (YOUR_NUMERIC_ID, TRUE, 0, '', 'ai')
ON CONFLICT (id) DO UPDATE SET enabled = TRUE;
```

Replace `YOUR_NUMERIC_ID` with the identified integer. Then register:

```powershell
.\deploy\bale-admin.ps1 -Action Register -Origin https://YOUR-SERVICE.onrender.com
```

The helper reads `WEBHOOK_SECRET` from `.env`; make it match the deployed value.
Render may generate its own secret through the blueprint, so reconcile these
values privately before registration.

## Switch receivers

To move from webhook to polling:

1. Stop the webhook deployment.
2. Run `bale-relay delete-webhook`.
3. Set `RECEIVER_MODE=polling`.
4. Run `bale-relay poll`, `bale-relay worker` and `bale-relay media-worker`
   as separate processes against the same database.

Polling checks the remote webhook and uses an expiring database lease to reject a
second poller. Offsets advance after ingestion.

To return to webhook mode, stop the poller, set `RECEIVER_MODE=webhook`, start the
web deployment and register its origin. An active polling lease blocks CLI
registration; after a hard stop, wait for the lease to expire.

`bale-relay serve` runs only the local development HTTP server on
`127.0.0.1:5000`; it does not start either worker.

## Recovery and monitoring

Free hosts may sleep or restart. `/status` resumes paused media work. Unknown sends
and uncertain AI generations require explicit `/retry JOB_ID`; retries can
duplicate an external action. Completed video parts are skipped after recovery.

The video pipeline targets 360p, with an eight-minute processing pass, at most
60 minutes of source duration, 250 MB downloaded, ten parts and 45 MB per part.
Local files are temporary. Completed Bale file IDs can be reused for seven days.

Use `bale-relay doctor` for configuration, tool and schema checks.
`bale-relay doctor --live` additionally checks Bale identity and configured AI
model discovery; it sends no chat messages and performs no generation or search.

`bale-relay stats` reports aggregate job states, lanes, attempts, processing
seconds, service-error counts and known downloaded/uploaded media payload bytes.
It excludes private text, user IDs, file IDs and credentials. Confirmed file
uploads count toward uploaded bytes; file-ID resends add no new upload payload.
Transfer totals exclude protocol overhead and do not replace host billing metrics.
Retries add their measured transfers. Apply all migrations before starting workers.

Bale's domestic availability does not guarantee its connection to a foreign host
during an outage. Verify the actual network path and run a limited invited-user
trial before relying on the deployment.
