---
name: doctor
description: Diagnose Summation (sum-api) connectivity and auth. Use when Summation calls fail, credentials seem stale, or the user asks whether Summation is set up correctly.
---

# Summation Doctor

Run the bundled diagnostic from the sibling `api` skill (resolve relative to this skill's base directory):

```bash
python3 ../api/scripts/sum_api.py doctor
python3 ../api/scripts/sum_api.py profiles
```

`doctor` reports: base URL, active profile, config file path and mode, OpenAPI reachability (title/version/path count), and whether M2M credentials or an access token are present.

Then prove auth end-to-end with one cheap call:

```bash
python3 ../api/scripts/sum_api.py call GET /v1/projects
```

## Interpreting results

- OpenAPI unreachable → network/base URL problem, not auth. Check the base URL against the active profile.
- `has_m2m_credentials: false` → no config found; hand off to the `login` skill.
- 401 on the list call → credentials invalid or expired; re-run `login`.
- 403 → scope problem; report the `request_id` and the scopes on the profile.
- Always include `request_id` from any failing response — it joins client failures to server-side traces.
