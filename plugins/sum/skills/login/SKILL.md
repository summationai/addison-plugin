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

## Rules

- Never print, log, or commit the client secret. It appears once, in the user's message; do not repeat it.
- Multiple environments → named profiles (`--profile`), switch with `use-profile <name>`.
- If `configure` cannot prompt interactively, pass all values as flags.
