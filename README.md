# Bale Relay

Independent Python bot for private Bale chats, with AI, Google search and YouTube delivery.
Implementation is in progress. This checkout currently includes the durable ingress/queue,
access control, migrations, provider adapters and their tests. The text dispatcher and durable outbound delivery ledger are implemented. The
YouTube pipeline and deployment bundle now have an initial implementation; real media and deployment verification remain outstanding.
Local verification is complete; treat the first foreign-host deployment as an experimental pilot until live AI, Google, YouTube and several-day operation pass.

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

Earlier local schema validation: all four migrations matched the
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

## Verification automation

The GitHub workflow runs Python 3.12 tests with a disposable PostgreSQL service and
ffmpeg, builds the Docker image, starts its web/text/media processes against the
test database, checks `/healthz`, verifies an unapproved user's webhook is denied,
and checks the container's ffmpeg/ffprobe/Deno/yt-dlp executables. This workflow has
been authored but not executed in this session; it requires pushing the commit.
No provider keys or chat recipients are configured in these automated checks.

`TEST_POSTGRES_URL` enables three real database contention tests. Each uses a unique
temporary schema and removes it afterward. Supply a disposable test database, never
a production DSN. With no URL they explicitly skip.

Provider regression tests cover all five AI adapters, deny unapproved models and
verify no automatic provider fallback. Google tests cover independent-quota
attestation, cross-instance caching and the 200-attempt monthly fail-closed limit.
These are mocked upstream responses and do not prove live provider availability.

## Latest local evidence

The official ffmpeg Windows shared archive (91,000,239 bytes) was downloaded from
`yt-dlp/FFmpeg-Builds` and checked against the release API SHA-256 digest. The real
media test now passes: it exposed and fixed an input-seek bug that retained an
older GOP in later parts. Output seeking at selected keyframes avoids that overlap.

With the downloaded tools on PATH, the suite has 56 cases: 53 pass, including actual
ffmpeg generation/splitting; three PostgreSQL tests skip without TEST_POSTGRES_URL.
The official yt-dlp 2026.10.26 module executes locally. A read-only request to the
public yt-dlp test video failed with a connection reset from the YouTube path;
live YouTube availability from the eventual foreign host is still unverified.

PyPI is still unreachable here. The independent virtualenv is incomplete. Local
unit tests currently use the existing wartime-mirror Python environment with this
repository's src on PYTHONPATH; the bot source has no runtime dependency on that
repository. Docker, PostgreSQL and live Bale/provider credentials remain separate
verification gates. No commit has been pushed to GitHub during this session.

See `deploy/ACCEPTANCE.md` for requirement-by-requirement evidence and remaining
verification. Current local suite: 59 cases, 56 pass, three PostgreSQL skips.
Video upload bodies now stream in 64 KiB chunks instead of requests' buffered file
multipart mode; actual localhost HTTP verifies content length and body correctness.
Upload timeout is capped by the remaining media pass deadline, with cancellation
and deadline checkpoints while reading the file.

## Live read-only checks so far

Bale `getMe` succeeded using the locally configured token. Gemini discovery reported
an unsupported user location; OpenRouter discovery returned HTTP 403. Regional or
host-policy denials are now represented separately from HTTP 401 authentication
failures. No raw provider error body or credential appears in diagnostics.
`doctor --live` now also checks configured AI providers' model-list endpoints; it
still performs no text generation or Google search and sends no chat message.

Latest local suite: 61 cases, 58 pass and three PostgreSQL tests skip. Operator setup
is in progress: Neon PostgreSQL, independent SerpApi quota and the test user's numeric
Bale ID are not yet supplied. AI model allowlisting remains fail-closed.

## Trial monitoring

`bale-relay stats` prints aggregate job states, lanes, attempt counts, processing
seconds, service-error count and known media payload bytes downloaded/uploaded.
It does not return chat text, model prompts, user IDs, file IDs or credentials.
Uploaded bytes count confirmed file uploads; file-ID resends have no new upload
payload. Numbers exclude HTTP/protocol overhead and do not replace host billing
usage. Retries add their actually measured transfer counts. Apply migration 0005
before starting updated workers.

Docker and CI now install direct versions from `requirements-runtime.txt`. The six
core framework/client versions match the locally tested environment. Psycopg and
Gunicorn pins were checked against official upstream release tags, but have not
been installed/executed locally. This file pins direct packages; transitive versions
and system binaries still need a fully resolved deployment lock/build verification.
The current suite has 64 cases: 61 pass, including actual media/HTTP tests, and
three PostgreSQL contention cases skip. Five migrations match model metadata on
SQLite. `doctor` resolves the migration head from Alembic rather than a hardcoded ID.

## Final local verification

All 64 tests passed with no skips using real PostgreSQL 16.15 and ffmpeg. All five
Alembic migrations ran on PostgreSQL and schema comparison returned no differences.
The temporary localhost-only PostgreSQL instance was stopped and removed afterward.
The psycopg 3.3.8 Python implementation used official source and the verified test
bundle's libpq. No production database or user data was used for these tests.

For setup on Windows without installing the Python CLI, use the dependency-free
PowerShell helper from the repository root:

```powershell
.\deploy\bale-admin.ps1 -Action Identify
.\deploy\bale-admin.ps1 -Action Register -Origin https://YOUR-SERVICE.onrender.com
```

Identify must be run before webhook registration. It asks you to send a random
marker to your bot and returns only the matching private sender's numeric ID.
Register reads BALE_TOKEN and WEBHOOK_SECRET from the ignored local .env and never
prints the secret webhook URL. Copy the exact same WEBHOOK_SECRET into Render.

Once the container has created tables, allow that ID using Neon's SQL Editor:

```sql
INSERT INTO bot_users (id, enabled, generation, model, mode)
VALUES (YOUR_NUMERIC_ID, TRUE, 0, '', 'ai')
ON CONFLICT (id) DO UPDATE SET enabled = TRUE;
```

Docker build/startup, Render/Neon account setup and real foreign-host provider
availability are not established by the local test suite. The CI workflow is
prepared to check Docker on a runner. Model allowlisting must be supplied by the
operator using free model identifiers; an empty list intentionally disables AI.
