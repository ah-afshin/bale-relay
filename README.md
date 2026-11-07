# Bale Relay

Independent Python bot for private Bale chats, with AI, Google search and YouTube delivery.
Implementation is in progress. This checkout currently includes the durable ingress/queue,
access control, migrations, provider adapters and their tests. The text dispatcher and durable outbound delivery ledger are implemented. The
YouTube pipeline and deployment bundle are still being built.
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
- YouTube search, controlled downloads, actual byte caps, lossless splitting and resume.
- Render Docker bundle with both web and worker; polling exclusivity.
- PostgreSQL concurrency tests, real ffmpeg tests and sleep/restart recovery.
- Live Bale/Neon/AI/search smoke test with operator credentials.
- Several days of invited-user operation before relying on the service.

Bale's domestic availability does not guarantee its foreign API connection survives
an outage. Messages pass through Bale and AI providers. `/forget` can only remove
application-controlled data, not copies held by third parties.
