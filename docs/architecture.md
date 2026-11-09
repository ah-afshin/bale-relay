# Architecture

Bale Relay is a standalone package. It does not require the source, runtime or
credentials of another application.

## Components

| Location | Responsibility |
| --- | --- |
| `entrypoints/` | CLI, Flask webhook, polling, workers, diagnostics and container supervisor |
| `bot/` | Commands, Persian menus and conversation dispatch |
| `services/` | AI and Google feature logic, independent of Flask |
| `adapters/` | Bale transport, bounded YouTube subprocesses and streaming multipart uploads |
| `core/` | Configuration, shared HTTP client, security checks and errors |
| `storage/` | Database models, durable queues, caches and delivery state |
| `migrations/` | Alembic schema revisions |

## Ingestion and access

The webhook validates its secret and accepts only approved private users whose
sender ID matches the chat ID. Inbound updates are persisted before acknowledgment;
duplicate update IDs do not create duplicate jobs. Inline actions reference stored
state and are restricted to their owner and active conversation generation.

Polling uses the same ingestion path, commits offsets after ingestion, refuses an
active remote webhook and holds an expiring database lease to exclude a second
poller. Webhook and polling receivers must not run together.

## Processing and recovery

Text and media have separate workers. Keep one of each in the current prototype.
Production uses PostgreSQL for state that must survive process and host restarts.
Local media files are temporary rather than durable state.

AI jobs persist an in-flight marker before generation. Completed replies and their
history are saved together and reused after recovery. An interrupted in-flight
generation has an unknown outcome and needs explicit `/retry JOB_ID` authorization
before another provider call. Outbound delivery has its own durable ledger.
External APIs do not provide an exactly-once guarantee; retries of uncertain sends
may create duplicates.

Media processing records part delivery, skips completed parts on recovery and
reuses completed Bale file IDs for seven days, scoped to the bot token. Uploads
stream in chunks of at most 64 KiB, with cancellation and deadline checkpoints.
Processing limits are documented in the [operator guide](../deploy/README.md).

Google results use a database-backed cache shared across processes and restarts.
Keys are query digests scoped to the SerpApi key. Quota reservations are atomic and
associated with jobs so recovery does not reserve the same usage again.

## Boundaries

Bale, AI and Google use the shared HTTP client. YouTube uses its controlled
downloader with validated video IDs, bounded subprocess lifetime and media limits.
Do not introduce arbitrary outbound URLs or shell fragments. Tokens, secret paths,
full inbound payloads and private messages must not appear in logs.
