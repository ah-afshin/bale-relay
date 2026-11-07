# Acceptance evidence and outstanding gates

This document tracks the original agreed scope. No deployment or live-service success
is inferred from mocked test responses.

| Requirement | Current evidence | Remaining verification |
|---|---|---|
| Independent bot repository, no website relay | Package imports only bale_relay; separate Git history | Fresh install on Python 3.12 |
| Durable authenticated webhook and duplicate handling | Ingress regression tests; Alembic schema comparison | PostgreSQL contention and real Bale webhook |
| Private invited users and owned callbacks | Ingress/conversation tests; deny foreign and stale buttons | Invited-user trial |
| Five AI providers and explicit free allowlist | All five provider adapter regression cases; allowlist/fallback tests | Operator-approved keys/models and live generation |
| Ordered AI history, deletion and seven-day retention | Conversation and retention tests, generation checkpoint/recovery | PostgreSQL deletion/generation race test |
| Google results, persistent cache and 200 monthly cap | Provider tests prove cache reuse and quota fail-closed | Live SerpApi key with independent free quota |
| YouTube search, preview and select/download | Dispatcher commands and owned inline actions; constrained adapter tests | Live foreign-host search/download |
| 360p, 60 min, 250 MB, ten 45 MB parts | Limits in adapter; synthetic actual ffmpeg media tests | Real long video, disk-full and actual byte-limit interruption |
| Bounded process lifetime and cancellation | Downloader process deadlines; upload checkpoint tests | Hard process termination on deployed host |
| Part recovery, file-ID reuse, unknown-send explicit retry | Media/cache/recovery tests | Real Bale file-ID reuse and interrupted upload |
| Low-memory uploads | Actual localhost HTTP multipart exchange, <=64 KiB body chunks | Resident-memory measurement on free host |
| Persistent PostgreSQL | Models/migrations and conditional concurrency tests prepared | TEST_POSTGRES_URL required; those tests have not run |
| Webhook/polling exclusivity and durable offset | Recovery tests; CLI registration/delete and expiring poll lease | Live transport switching |
| Docker web+text+media supervisor | Dockerfile, Render blueprint, CI container-start smoke authored | Docker build and workflow execution |
| Repeatable dependencies | yt-dlp and Deno pinned; source dependencies bounded | Full runtime dependency lock and fresh build |
| Free no-card hosting | Render/Neon configuration prepared | Operator account availability and quota checks |
| Real network emergency path | No evidence yet | Bale <-> foreign host test; no domestic-availability guarantee |
| Several-day limited trial | Not started | Host, credentials, approved users and observation |

Local suite: 59 cases, 56 passing and three PostgreSQL cases skipped. Actual ffmpeg
splitting passes with checksum-verified official binaries. Read-only YouTube metadata
from the current machine failed with a connection reset. PyPI installation still
fails from the current network. GitHub release downloads work through curl.

No real tokens are present in this repository's `.env` at the last inspection. Place
credentials in the ignored local `.env` or host secret settings, never in commits or
chat. Use `.env.example` as the key list. A real smoke test also needs the owner's
numeric Bale user ID. The source website's `.env` is not copied or inspected.
