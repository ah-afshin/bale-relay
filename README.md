# Bale Relay

A standalone Python bot for private Bale chats, with Persian menus, AI conversations,
Google search through SerpApi, and YouTube video delivery. Access is limited to users
explicitly approved by the operator.

The project is experimental. Automated tests cover persistence, access control,
recovery and provider adapters; deployment and live provider availability must be
verified on the intended host. Availability inside Iran does not guarantee that
Bale can reach a foreign-hosted bot during an internet outage.

## Features

- AI conversations with model selection across Gemini, Groq, OpenRouter, Cerebras
  and Mistral. Only operator-approved models are available, with no automatic fallback.
- Google search with a persistent cache and usage limits.
- YouTube search, previews and bounded video downloads, with resumable delivery.
- Durable inbound queues, separate text and media workers, and webhook or polling reception.
- Private-chat access checks, user-owned buttons, daily quotas and conversation deletion.

## Quick start

Use Python 3.12 or later. Run these commands from the repository root. This example
uses PowerShell and SQLite for local development; production requires PostgreSQL.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
Copy-Item .env.example .env
```

Edit `.env`: set `BALE_TOKEN` and `RECEIVER_MODE=polling`. To enable AI, add a
provider key and explicitly approved `AI_ALLOWED_MODELS` entries as described in
[Configuration](docs/configuration.md). An empty allowlist disables AI.

Initialize the database and approve your numeric Bale user ID:

```powershell
alembic upgrade head
bale-relay allow-user 123456789
```

Replace the example ID with your own. For a new bot on Windows, the
[identity helper](deploy/README.md#windows-identity-and-registration-helper) can
find your ID before you start a receiver.

If the bot already has a webhook, stop its existing receiver and run
`bale-relay delete-webhook` before starting polling. Run each of these commands in
a separate terminal, with the same virtual environment activated and working directory:

```powershell
bale-relay poll
```

```powershell
bale-relay worker
```

For YouTube, also install `python -m pip install -e ".[media]"`, make `ffmpeg`,
`ffprobe` and Deno available on `PATH`, and start `bale-relay media-worker` in
another terminal. The Docker image includes these tools.

## Using the bot

Send `/start` in an approved private chat to open the Persian menu.

| Command | Action |
| --- | --- |
| `/ai`, `/model` | Enter AI mode and select an approved model |
| `/new` | Start a new conversation |
| `/search query` | Search Google |
| `/youtube query` | Search YouTube |
| `/video ID`, `/download ID` | Preview or request a video by its YouTube ID |
| `/status` | Show recent jobs and resume paused work |
| `/cancel` | Cancel current work |
| `/retry JOB_ID` | Explicitly retry an eligible job; an uncertain send may be duplicated |
| `/forget`, `/privacy` | Delete application-controlled conversation data or read the privacy notice |

## Privacy and reliability

Messages pass through Bale and the selected service providers. Conversation history
has a seven-day retention window; `/forget` cannot delete copies held by third
parties. Keep `.env`, credentials, private messages and secret webhook paths out of
logs and Git history.

Inbound updates are persisted before acknowledgment. Recovery avoids automatically
repeating uncertain AI calls or sends, but delivery across external APIs is not
guaranteed to happen exactly once. Only explicitly approved private users can use the bot.

## Documentation

- [Configuration and provider setup](docs/configuration.md)
- [Deployment, receiver switching and operations](deploy/README.md)
- [Architecture and recovery behavior](docs/architecture.md)
- [Contributing and running tests](CONTRIBUTING.md)
- [Verification scope and deployment acceptance](deploy/ACCEPTANCE.md)
- [Security reporting](SECURITY.md)

## License

[MIT](LICENSE) - Copyright (c) 2026 ah-afshin.
