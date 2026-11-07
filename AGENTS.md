# Project guidelines

Keep this bot independent of wartime-mirror. Feature services must not import Flask.
Preserve default-deny identity checks and persist inbound updates before acknowledging.
Use the shared HTTP client for Bale, AI and Google; the YouTube adapter may use its
controlled downloader. Never accept arbitrary outbound URLs or shell fragments.
Never log tokens, webhook paths, full update payloads or private chat contents.
Use unittest and run `python -m unittest discover -v`. Production requires PostgreSQL.
