# Summation Claude Plugins

Plugin marketplace for Summation. One plugin, `sum`, exposes the public sum-api to Claude surfaces: live OpenAPI discovery, data questions, report generation and export (PDF/DOCX/Markdown).

## Install

**Claude Code (CLI/IDE):**

```
/plugin marketplace add summationai/claude-plugins
/plugin install sum@summationai
```

**claude.ai / Claude Desktop (org admins):** Admin console → Plugins → Add plugins → *Sync from GitHub* (this repo) or *Upload a file* (`dist/sum-plugin.zip`). Members then install from the org library.

> Desktop note: skill scripts run in the code-execution sandbox. The org's code-execution network egress must allow the sum-api host(s) (Capabilities → Code execution), and credentials must be reachable from the sandbox — see the dogfood matrix in the rollout doc.

**Codex:** the `api` skill is tool-agnostic; symlink `plugins/sum/skills/api` into `~/.codex/skills/summation`. (Installer script planned.)

## Contents

- `plugins/sum/skills/api` — OpenAPI-discovery skill + `scripts/sum_api.py` helper (the canonical helper; sibling skills reference it)
- `plugins/sum/skills/login` — conversational credential setup → `~/.summation/skill-config` (0600)
- `plugins/sum/skills/doctor` — connectivity/auth diagnosis

Credentials never live in this repo. `.summation-config*` is ignored and must stay that way.

## Dev loop

```bash
claude --plugin-dir ./plugins/sum        # load for one session
claude plugin validate ./plugins/sum     # validate manifest
./build-zip.sh                           # rebuild dist/sum-plugin.zip for org upload
```

## Release

Bump `version` in `plugins/sum/.claude-plugin/plugin.json` AND `.claude-plugin/marketplace.json` (users only receive updates on version bumps).
