# Security

## Supported versions

There is no numbered release yet. Security fixes apply to the `main` branch of this repository.

## Reporting a vulnerability

Use GitHub private vulnerability reporting for this repository. Do not open a public issue for a suspected vulnerability.

If private reporting is not enabled yet, contact the maintainer directly and wait for this path to be turned on. Do not send credentials, crawl databases, or live session cookies in the report. Describe the component, the conditions, and the impact.

## Operational expectations

The crawler fetches URLs supplied by its operator. TLS verification is on by default. Private and link-local destinations, including cloud metadata addresses, are refused unless `security.allow_private_networks` is explicitly set to `true`. Redirects are not followed. Response bodies, the in-memory queue, and per-page link lists are size-capped.

Those controls do not make the crawler safe to point at arbitrary networks. Read the threat model in `README.md` before running it.
