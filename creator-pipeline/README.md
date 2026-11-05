# Creator Pipeline skill

A Claude skill that keeps your creator outreach CRM in sync with your cold email campaigns and drafts the replies for you.

It reads every creator reply to your Instantly cold campaigns from two places: the Gmail inbox you CC on every outbound, and the Instantly API (which also holds the replies to auto follow-up steps that never reach your CC). It merges the two, works out where each creator is (replied, engaged, at the CTA, converted, gone quiet, declined), updates a Notion "Creator Pipeline" database, and drafts a threaded reply in Gmail for every creator waiting on you, pushed towards that campaign's goal (fill in a form, book a call, sign an agreement). It learns each campaign's reply playbook by asking you once, and it never sends anything: drafts only.

## What you need

- Claude Code or the Claude desktop app (skills support).
- **Gmail connector** (Composio, a Gmail MCP, or similar) signed in to the inbox you CC on cold outbound. Its draft tool must support replying inside a thread (a `thread_id`). Composio's `GMAIL_CREATE_EMAIL_DRAFT` does.
- **Instantly**, connected through Composio (Instantly toolkit) or the Instantly API.
- **Notion MCP**, with access to the two databases below.

## Notion setup

Create two databases (ideally on one hub page) and share them with your Notion integration.

**1. Creator Pipeline**

| Property | Type | Options |
|---|---|---|
| Creator | Title | |
| Handle | Text | |
| Email | Email | |
| Status | Select | Sent, Reply Received, Engaged, Conversion Pending, Converted, Follow Up, Ghosted, Declined |
| Action | Select | Reply Required (red), Waiting for Creator (blue), Waiting for Brand (purple), No Action |
| Source | Select | Instantly Campaign (add others you use) |
| Owner | Select | Your team members' names |
| Last Contact | Date | |
| Next Follow Up | Date | |
| Auto-Cadence Suppress | Checkbox | |
| Conversion Goal | Text | |
| CTA Link | URL | |
| Thread | URL | |
| Campaign Name | Text | |
| Instantly Campaign ID | Text | |
| Instantly Lead ID | Text | |
| Notes | Text | |

**2. Campaign Registry**

| Property | Type | Options |
|---|---|---|
| Campaign Name | Title | |
| Instantly Campaign ID | Text | |
| Status | Select | Active, Paused, Closed, Training Needed |
| Conversion Goal | Text | |
| CTA Link | URL | |
| Subject Pattern | Text | |
| Sending Account Pattern | Text | |
| Reply Flow | Text | |
| Sample Sequence Copy | Text | |
| Last Trained | Date | |
| Notes | Text | |

Property names must match exactly (the skill writes to them by name). Then copy each database's id from its URL, and its data source id (run `notion-fetch` on the database once to see it).

## Install

1. Unzip this folder.
2. Put the `creator-pipeline` folder in your skills directory: `~/.claude/skills/creator-pipeline/` (or a project's `.claude/skills/`).
3. Open `SKILL.md` and fill in the **Agency config** table at the top: your agency name, sender name and inbox, every sending domain you use in Instantly, the Notion database and data source ids, and your Gmail account id if your connector needs one.
4. Leave campaign goals and CTA links out of the config. The skill asks you for them per campaign on its first run and stores them in the Campaign Registry.

## Use

```
/creator-pipeline
```

The first run finds every active Instantly campaign and asks you five quick questions about each (conversion goal, CTA link, how to answer the common replies, subject pattern, sending account). After that, each run syncs the CRM, drafts replies for creators waiting on you, and gives you a report: drafts created, replies it couldn't match to a pattern, conversions, follow-ups due and possible duplicates. Ask for a "full sweep" if you want it to look beyond the creators currently waiting on you.

Review the drafts in Gmail, tweak them, and send them yourself.
