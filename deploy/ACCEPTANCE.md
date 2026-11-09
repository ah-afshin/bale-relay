# Verification scope and deployment acceptance

Use this checklist when evaluating a revision for deployment. Automated tests,
local integration tests and live-host checks establish different things. Mocked
provider responses do not prove live availability.

## Automated coverage

Run `python -m unittest discover -v` as described in
[Contributing](../CONTRIBUTING.md#tests). PostgreSQL tests require
`TEST_POSTGRES_URL`; real-media tests require ffmpeg and ffprobe. Record skips
explicitly rather than treating them as integration passes.

| Area | Repository coverage | Additional acceptance check |
| --- | --- | --- |
| Access and ingestion | Private identity checks, duplicate updates, owned/stale buttons | Real Bale webhook with approved and unapproved users |
| Conversation and deletion | History, generation checkpoints, retention and deletion | Deletion/generation races on the deployed database |
| AI | Five adapters, model allowlist, no automatic fallback, recovery | Approved no-charge models and actual generation from the host |
| Google | Independent-quota gate, shared cache, monthly cap | Independent SerpApi account and live search |
| YouTube | Validated IDs, metadata constraints, bounded subprocesses | Live search/download from the host |
| Media splitting | Generated H.264/AAC sample, actual byte caps, continuous time ranges | Long video, disk exhaustion and download interruption |
| Delivery and recovery | Durable ledger, retries, part recovery, file-ID cache | Interrupted upload, restart and real Bale file-ID reuse |
| Upload memory | Localhost HTTP multipart exchange, bounded chunks | Resident memory and deadline behavior on the host |
| PostgreSQL | Duplicate-ingress, quota and job-claim contention tests | Migrations and recovery against deployment-equivalent PostgreSQL |
| Receivers | Polling lease, durable offsets, webhook exclusivity | Live switching between webhook and polling |
| Packaging | Direct dependency pins and container smoke workflow | Fresh build, startup and complete dependency reproducibility |
| Operations | Content-free aggregate metrics | Several-day invited-user trial with host usage monitoring |
| Network path | No automated outage guarantee | Bale-to-host connectivity under the intended network conditions |

The [GitHub workflow](../.github/workflows/tests.yml) runs PostgreSQL and ffmpeg
tests, builds Docker, starts web/text/media processes, checks `/healthz`, verifies
default-deny webhook access and checks media executables. Check the workflow result
for the target revision; the presence of a workflow file is not a passing result.
It uses test credentials and does not validate live providers.

## Historical local verification

The previous development record reports 64 tests passing without skips against a
temporary PostgreSQL 16.15 instance and real ffmpeg. It also reports all five
Alembic migrations applied with no differences from model metadata. These are
historical local results, not a current CI or deployment certification.

Earlier network checks did not establish live AI generation or YouTube downloads
from the eventual host. Per-machine dependency failures, local credential setup
and successive intermediate test counts are not maintained as project status.

## Before relying on a deployment

- Confirm a fresh image builds and starts with persistent PostgreSQL and migrations.
- Validate credentials, approved users and model access from the actual host.
- Exercise AI, search, video delivery, cancellation and explicit retry behavior.
- Test sleep/restart recovery and inspect resource use without logging private data.
- Confirm hosting and provider quota/billing settings and complete an invited-user trial.

Record the revision, environment, commands, outcomes and skipped checks in a release
or deployment record. Do not include credentials, private messages or secret URLs.
