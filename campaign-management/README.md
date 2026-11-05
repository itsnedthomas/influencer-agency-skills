# Campaign Management skill

A Claude skill for running the email side of an influencer marketing campaign.

You give it the latest creator export (CSV) from your campaign portal. It checks where each creator really is (accepted, content submitted, amending, approved, live, awaiting payment), compares that with what you've actually emailed them, and drafts the right next email wherever there's a gap. It writes in your voice by learning from your Sent folder, and it never sends anything: drafts only.

## What you need

- Claude Code or the Claude desktop app (skills support).
- A Gmail connector (Composio, a Gmail MCP, or similar) signed in to the mailbox you send campaign emails from.
- A campaign portal or tracker that exports one row per creator with a status column.

## Install

1. Unzip this folder.
2. Put the `campaign-management` folder in your skills directory, for example `~/.claude/skills/campaign-management/` (or a project's `.claude/skills/`).
3. Open `SKILL.md` and fill in the **Campaign config** table at the top: your name, sending address, brand, handle, hashtags, portal link pattern and CSV filename.
4. If your portal uses different status names or CSV columns, edit the **Campaign progression flow** table and the expected columns list to match.

## Use

```
/campaign-management ~/Downloads/your-campaign-export.csv
```

You'll get a report of drafts created, portal/CSV mismatches to fix, and any creators who still need cold outreach. Review the drafts in Gmail, tweak them, send them yourself. Your edits become the template for next time.
