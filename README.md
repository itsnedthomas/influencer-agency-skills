# Influencer Agency Skills for Claude

Three Claude skills that run the day-to-day of an influencer marketing agency, from finding creators to getting them paid. They were built and refined on live campaigns, and every rule in them comes from a real mistake or a real correction.

| Order | Skill | What it does | Command |
|---|---|---|---|
| 1 | [find-creators](find-creators/) | Starts from a few seed Instagram handles, expands to related creators, enriches and filters them (niche, gender, location, has an email), ranks them and writes a Google Sheet ready for outreach | `/find-creators` |
| 2 | [creator-pipeline](creator-pipeline/) | Syncs creator replies from your cold email campaigns (Instantly) and Gmail into a Notion CRM, sets each creator's status and next action, and drafts replies | `/creator-pipeline` |
| 3 | [campaign-management](campaign-management/) | Once creators are on a campaign, audits each one's portal status against their email thread and drafts the right next email (shortlist, content chase, amends, green light, payment) | `/campaign-management` |

All three write **drafts only**. Nothing is ever sent without you reviewing it first.

## Install

1. Clone or download this repo.
2. Copy the skill folders you want into your skills directory, e.g. `~/.claude/skills/` (or a project's `.claude/skills/`).
3. Open each `SKILL.md` and fill in the config table at the top with your own details (name, sending address, brand, accounts, IDs).
4. Read each skill's own `README.md` for the tools and connections it needs.

## What you'll need

- Claude Code or the Claude desktop app.
- A Gmail connector (e.g. Composio or a Gmail MCP) for the mailbox you send from.
- For `creator-pipeline`: Instantly and Notion.
- For `find-creators`: the API keys listed in its README, and Google Sheets access.
- For `campaign-management`: a campaign portal or tracker that exports one row per creator with a status column.
