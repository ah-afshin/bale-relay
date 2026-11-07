# Bale Relay

Independent Python bot for private Bale chats, with AI, Google search and YouTube delivery.
Implementation is in progress. This checkout currently includes the durable ingress/queue,
access control, migrations, provider adapters and their tests. The text dispatcher and durable outbound delivery ledger are implemented. The
YouTube pipeline and deployment bundle now have an initial implementation; real media and deployment verification remain outstanding.
Do not deploy this partial checkout as a working emergency service.

## Development

Python 3.12+ is required. From this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
Copy-Item .env.example .env
alembic upgrade head
bale-relay allow-user 123456789
bale-relay serve
python -m unittest discover -v
```

The production configuration rejects SQLite. Use a Neon PostgreSQL URL with TLS;
all state must survive a Render restart. Never commit `.env` or tokens.
The webhook secret must be independent from the Bale token; disable HTTP access logs
in deployment because the secret is part of the path. Only private chats whose sender
matches the chat ID and an enabled administrator-provisioned user are accepted.

Provider adapters are copied from the user's wartime-mirror repository and import
only this package. Discovery does not prove a model is free. AI_ALLOWED_MODELS must
contain only explicitly approved model IDs on no-charge provider accounts.
Google search remains disabled until SERPAPI_INDEPENDENT_QUOTA=1 confirms that this
key's quota is independent from the original website. No automatic paid fallback.

## Remaining acceptance gates

- Further crash/concurrency verification of the conversational worker and delivery ledger.
- Real media verification against yt-dlp/ffmpeg and actual restart behavior.
- Docker build verification and runtime dependency lock.
- PostgreSQL concurrency tests, real ffmpeg tests and sleep/restart recovery.
- Live Bale/Neon/AI/search smoke test with operator credentials.
- Several days of invited-user operation before relying on the service.

Bale's domestic availability does not guarantee its foreign API connection survives
an outage. Messages pass through Bale and AI providers. `/forget` can only remove
application-controlled data, not copies held by third parties.

## Receiver and recovery commands

After migrations and access provisioning:

```powershell
bale-relay set-webhook https://your-service.onrender.com
bale-relay webhook-info
```

To move to polling, stop the webhook deployment, run `bale-relay delete-webhook`,
set `RECEIVER_MODE=polling`, and run `bale-relay poll`. Run the text and media workers
separately. Polling checks the remote webhook and holds an expiring database lease;
a second poller is rejected. Received offsets are committed only after ingestion.
`webhook-info` prints only whether a webhook exists, never its secret URL.

Bale commands: `/youtube query` lists videos, `/video ID` previews metadata and
`/download ID` queues delivery. `/status` resumes paused work. `/retry JOB_ID`
explicitly authorizes retrying a failed or unknown send and may produce duplicates.
Each retry is restricted to the original owner and active conversation generation.
Completed video's file IDs are reused for seven days, scoped to the bot token.

Current local validation: 43 unittest cases passed; all four migrations match the
SQLAlchemy metadata on SQLite. PostgreSQL and actual media tools are not yet tested.
Installing a fresh environment failed because connections to PyPI timed out. No
ffmpeg, Docker or PostgreSQL runtime was found in the checked installation paths.

The bot now presents Persian inline menus. Model and video selection callbacks
reference stored actions and are checked against their owner and conversation
generation. Copying a button to another user or reusing it after `/new` is rejected.
All user and global daily limits are configurable in `.env.example`.

Google results use a database-backed cache shared across restarts/processes. Cached
keys are SHA-256 digests scoped to the configured SerpApi key; raw query strings
are not stored as cache keys. Atomic per-job quota reservations prevent duplicate
usage charges when the same job is recovered.

AI jobs persist an in-flight marker before generation and save the completed reply
with history in one transaction. A recovered in-flight generation becomes unknown;
only `/retry JOB_ID` authorizes another provider call. A completed reply is reused
without generating it again. These behaviors are covered by local regression tests;
they do not claim exactly-once delivery across provider/network boundaries.

## Readiness check

`bale-relay doctor` checks required tools, configuration, schema and migration state.
It prints only boolean results and exits nonzero if any required check fails.
`bale-relay doctor --live` additionally verifies the bot token with Bale `getMe`;
it does not generate AI replies, consume Google searches or send chat messages.

Install media/server extras with `pip install -e ".[media,server]"`. The official
yt-dlp 2026.10.26 package has been imported locally; its version is pinned for media
installs. Other runtime versions and the Docker image still need reproducible-build
verification. Locally downloaded binaries are ignored under `.tools/`.

The actual ffmpeg test is `tests.test_media_real`: it generates H.264/AAC media,
splits at keyframes, checks every output's real byte size and duration, and verifies
continuous intended time ranges. If ffmpeg/ffprobe are missing it reports a skip;
a skipped result does not satisfy the real-media acceptance gate.
