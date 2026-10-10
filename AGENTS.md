# Agent notes

This repository is a single-process async crawler with a CLI, a separate metrics process, Compose files, and an unverified Kubernetes example.

## Scope

Preserve the existing crawler, CLI, and SQLite schema. Do not rewrite it into a distributed system, and do not claim PostgreSQL, Grafana dashboards, retries, or horizontal scaling work unless the code does those things.

The container base is the Docker Official Image `python:3.11-slim`. Do not describe it as a Docker Hardened Image. Official Hardened Images are published from `dhi.io` and are not configured here.

## Verification

Run the unit tests and `docker compose config --quiet` after code or Compose changes. Tests must use localhost fixtures or mocks. Do not crawl third-party websites. Do not start the default container command as a test: `config.json` lists `https://example.com`.

Do not report a check as passed unless that command exited successfully in this workspace.

## Secrets and data

Do not commit `.env`, database files, crawl exports, logs, or private keys. `.env.example` may contain only obvious placeholders. Do not print secret values in logs, diffs, or reports. Do not rewrite Git history or rotate credentials without explicit approval.

## Approval gates

Do not create a GitHub repository, push, change visibility, publish an image or package, enable paid security products, or install a GitHub App unless the maintainer approves that exact action. Default to a private repository for the first push. Do not add a license unless the maintainer chooses one.
