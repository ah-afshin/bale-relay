# Configuration

Copy `.env.example` to `.env` for local commands. The CLI and Alembic load it from
the working tree; in Docker and hosted deployments, supply environment variables.
Never commit `.env` or paste its contents into an issue.

## Core settings

| Variable | Meaning |
| --- | --- |
| `APP_ENV` | `development` by default; use `production` on the deployed host |
| `DATABASE_URL` | Local default: `sqlite:///instance/relay.sqlite3`; production requires persistent PostgreSQL |
| `BALE_TOKEN` | Token for this bot |
| `WEBHOOK_SECRET` | Independent random secret of at least 32 characters; required in production, including polling mode |
| `RECEIVER_MODE` | `webhook` by default, or `polling` |
| `PORT` | Container HTTP port; defaults to `10000` |

PostgreSQL URLs beginning with `postgres://` or `postgresql://` are normalized to
the psycopg driver. Use TLS for remote databases, for example with
`?sslmode=require`. State must survive host restarts.

Generate a webhook secret separately from the Bale token, store it privately, and
use the same value for the receiver and registration. Production rejects a missing
token, a short secret, a secret equal to the token, or a SQLite database.

## AI providers

Set the key for each provider you intend to use:

| Provider prefix | Key variable |
| --- | --- |
| `gemini` | `GEMINI_API_KEY` |
| `groq` | `GROQ_API_KEY` |
| `openrouter` | `OPENROUTER_API_KEY` |
| `cerebras` | `CEREBRAS_API_KEY` |
| `mistral` | `MISTRAL_API_KEY` |

`AI_ALLOWED_MODELS` is a comma-separated list of `provider/model-id` entries.
Replace `model-id` with the exact model identifier approved for that provider;
preserve any provider-native namespace after the first slash. The bot filters
model discovery against this list. An empty list intentionally disables AI.

Model discovery does not prove a model is free or that generation will work from
the deployment host. Verify account terms, model access and no-charge eligibility
before approving an entry. The application does not automatically fall back to
another provider or paid model.

## Google search and quotas

Google search uses `SERPAPI_API_KEY` and stays disabled until
`SERPAPI_INDEPENDENT_QUOTA=1` attests that the key has an independent free quota.
Do not share another application's quota. A persistent monthly cap rejects
requests after 200 reserved search attempts.

| Feature | Per-user daily variable (default) | Global daily variable (default) |
| --- | --- | --- |
| AI | `AI_DAILY_LIMIT` (20) | `AI_GLOBAL_DAILY_LIMIT` (200) |
| Search | `SEARCH_DAILY_LIMIT` (5) | `SEARCH_GLOBAL_DAILY_LIMIT` (100) |
| YouTube | `YOUTUBE_DAILY_LIMIT` (1) | `YOUTUBE_GLOBAL_DAILY_LIMIT` (10) |

Daily quotas use UTC dates. Values must be nonnegative integers. Per-job atomic
reservations prevent recovery from charging the same job twice.

## Diagnostics

`bale-relay doctor` checks configuration, tools, schema and migration state, prints
boolean results and exits nonzero when a required check fails. It checks the full
feature setup, so intentionally disabled AI or search can produce failed checks.

`bale-relay doctor --live` also calls Bale `getMe` and configured AI providers'
model-list endpoints. It does not generate AI text, consume Google searches or
send chat messages. Passing discovery checks does not establish live generation
or YouTube availability.
