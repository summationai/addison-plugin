---
name: login
description: Authenticate with Summation (sum-api). Use when the user needs to set up, fix, or switch Summation credentials or profiles, or when any Summation call fails with 401/403 and no valid config exists.
---

# Summation Login

Set up sum-api credentials conversationally. The helper lives in the sibling `api` skill: `<plugin>/skills/api/scripts/sum_api.py` (resolve relative to this skill's base directory: `../api/scripts/sum_api.py`).

## Flow

1. Ask the user for: base URL (default `https://sandbox-api.summation.com`), `client_id`, `client_secret`, and an optional profile name. Never echo the secret back.
2. Write the config:

```bash
python3 ../api/scripts/sum_api.py configure \
  --base-url <BASE_URL> --client-id <CLIENT_ID> --client-secret <CLIENT_SECRET> \
  [--profile <NAME> --activate]
```

   This stores `~/.summation/skill-config` with file mode `0600`.

3. Verify immediately:

```bash
python3 ../api/scripts/sum_api.py doctor
python3 ../api/scripts/sum_api.py call GET /v1/projects
```

4. Report: config path, active profile, and whether the authenticated list call succeeded (include `request_id` on failure).

## No credentials yet? (new-customer path)

If the user has no `client_id`/`client_secret` and no idea where to get them, do NOT dead-end. Explain: API credentials are issued by their Summation admin (or Summation support), then offer to draft the request for them:

> Subject: Summation API credentials for Claude
> Hi — I'm connecting Claude to Summation and need machine credentials: the API **base URL** for our tenant, a **client_id** and **client_secret** with scopes `agent:read agent:write`. Please share them securely (not over chat/email plaintext).

Tell them to come back with `/sum:login` once they have the three values — and that the values are stored locally with file mode 0600, never in this conversation's history beyond their one paste.

## Rules

- Never print, log, or commit the client secret. It appears once, in the user's message; do not repeat it.
- Multiple environments → named profiles (`--profile`), switch with `use-profile <name>`.
- If `configure` cannot prompt interactively, pass all values as flags.
