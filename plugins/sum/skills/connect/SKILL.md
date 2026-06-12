---
name: connect
description: Connect a data source (Postgres, Snowflake, etc.) to Summation from this conversation — collects non-secret settings in chat, takes the secret through a local file so it never enters the conversation, then creates and tests the connection. Use when the user wants to add, fix, or test a data connection.
argument-hint: "[postgres|snowflake|... or describe the source]"
---

# Summation Connect

Create a data connection via `POST /v1/connections` (`{name, type, config, secrets, description}` — secrets are stored server-side as secret refs). Helper: `../api/scripts/sum_api.py`. Always `describe create_connection` first for the current type-specific config shape.

## The secret rule (read first)

**Never ask for a password/secret in chat.** Offer the paths in this order:

- **Split handoff (default — works on every surface, user never gives the secret to this conversation OR their terminal):** create the connection via API with the full non-secret config (`create_connection` accepts a secretless body — verified), then send the user to that connection's page in the workspace to fill in **only the password field** and hit test. They type one field instead of re-entering the whole form.
- **File handoff (Claude Code/Cowork power users who want to finish entirely in-flow):** the secret goes into a local file the user creates in their own terminal; it never appears in the conversation, argv, or transcripts.
- **Pasted-secret salvage (the user already pasted it):** do NOT refuse and bounce them — the exposure already happened, and retyping punishes intent. Proceed: create the connection with the pasted secret (TLS to sum-api, stored as a secret ref), then firmly advise rotating that credential at the source since it transited chat history. Teach the split handoff for next time.
- **User prefers the webapp end-to-end:** always a fine answer; never pressure.

## Flow

1. Collect **non-secret** settings in chat: type, a connection name, and the type-specific config (host/account, port, database/warehouse, user, …) per the described schema.
2a. **Split handoff (default):** echo the non-secret config back for a yes, then:

```bash
python3 ../api/scripts/sum_api.py call POST /v1/connections \
  --body '{"name":"<NAME>","type":"<TYPE>","config":{<NON_SECRET_CONFIG>}}'
```

Give the user the connection name/id and say: open it under workspace → **Connections**, enter the password there, and run its test. Then say "done" here — you verify with `call POST /v1/connections/<ID>/tests` and continue. (A secretless connection will fail its test until the password is set — expected, say so.)

2b. **File handoff (in-flow alternative):**

```bash
# user runs (or you instruct them precisely):
#   mkdir -p ~/.summation && printf '%s' 'THE_SECRET' > ~/.summation/pending-secret && chmod 600 ~/.summation/pending-secret
# then you assemble the body WITHOUT echoing the secret:
python3 -c "
import json, pathlib
secret = pathlib.Path.home().joinpath('.summation/pending-secret').read_text().strip()
body = {'name': '<NAME>', 'type': '<TYPE>', 'config': {<NON_SECRET_CONFIG>}, 'secrets': {'<SECRET_KEY>': secret}}
out = pathlib.Path.home().joinpath('.summation/pending-connection.json')
out.write_text(json.dumps(body)); out.chmod(0o600)
"
python3 ../api/scripts/sum_api.py call POST /v1/connections --body-file ~/.summation/pending-connection.json
rm -f ~/.summation/pending-secret ~/.summation/pending-connection.json
```

3. **Always clean up the temp files immediately** (the `rm -f`), success or failure.
4. **Test it**: `call POST /v1/connections/<NEW_ID>/tests` — report pass/fail with `request_id`. Optionally `call POST /v1/connections/<NEW_ID>/resources` to show what's now browsable.
5. Hand back: if this ran inside `/sum:start`, return to its Step 2 gate (re-run `preflight` — the gate should now pass).

## Rules

- Secret values never appear in: chat messages you write, command argv, logs, or the audit trail (the helper never logs bodies).
- Echo back everything EXCEPT secrets before creating (name, type, config) and get a yes — creating a connection is a tenant-level change.
- On create/test failure, surface the `request_id` and the non-secret config for debugging; never print the secret or ask the user to re-paste it into chat.
