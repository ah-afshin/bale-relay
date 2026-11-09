# Contributing

Bug reports, documentation improvements and pull requests are welcome. Describe the
observed behavior, expected behavior and steps to reproduce a problem. Use synthetic
examples and remove credentials and private chat content. Report vulnerabilities
through the [security reporting process](SECURITY.md).

## Development setup

Follow the [quick start](README.md#quick-start) to create a virtual environment and
install the package. Work from the repository root so migrations and `.env` resolve
consistently. SQLite is suitable for local development; production requires PostgreSQL.

For the direct runtime versions used by Docker and CI:

```powershell
python -m pip install -r requirements-runtime.txt
python -m pip install --no-deps -e .
```

`requirements-runtime.txt` pins direct Python dependencies. It is not a complete
lock of transitive dependencies, base images or system tools.

## Tests

Use unittest:

```powershell
python -m unittest discover -v
```

Most tests use local SQLite databases and mocked provider responses. The multipart
test uses a local HTTP server. Tests do not require live provider keys or a bot recipient.

For PostgreSQL contention tests, supply an explicitly disposable database:

```powershell
$env:TEST_POSTGRES_URL = 'postgresql+psycopg://USER:PASSWORD@localhost/relay_test'
python -m unittest discover -v
```

These tests create unique temporary schemas and drop them afterward. Do not point
them at production. Without `TEST_POSTGRES_URL`, they report skips.

The real-media test requires `ffmpeg` and `ffprobe` on `PATH` and generates its own
H.264/AAC sample. It reports a skip if either tool is missing. A skipped test is
not verification of that integration.

The [verification workflow](.github/workflows/tests.yml) runs the suite with
PostgreSQL and ffmpeg, then builds and smoke-tests the Docker container. A workflow
definition alone does not establish that its checks passed; consult the run for
the revision you intend to deploy.

## Changes and review

- Keep the package independent of other projects; feature services must not import Flask.
- Preserve default-deny identity checks and durable ingestion before acknowledgment.
- Use the shared HTTP client for Bale, AI and Google. Keep YouTube downloads bounded
  by the controlled adapter; never accept arbitrary outbound URLs or shell fragments.
- Add migrations for persistent schema changes and verify recovery behavior when
  changing queue or delivery handling.
- Never include tokens, secret webhook paths, full inbound updates or private chat
  contents in logs, fixtures, issues or pull requests.
- Explain behavior changes and relevant test results in the pull request. Update
  documentation when configuration or commands change.

See [Architecture](docs/architecture.md) for component boundaries. `AGENTS.md`
contains repository instructions for coding agents. Contributions are made under
the repository's [MIT license](LICENSE).
