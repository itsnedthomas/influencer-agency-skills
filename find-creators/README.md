# find-creators

A Claude Code skill that turns a handful of seed Instagram handles into a ranked Google Sheet of lookalike creators ready for outreach.

It expands the seeds through Instagram's related-accounts graph (via Apify), enriches every profile, filters by vertical, gender, geography and whether there's a usable email, scores and ranks them, and writes every qualifying creator to a new sheet. Re-running with "give me more" goes deeper without re-paying for profiles it has already seen or re-listing anyone.

## What you need

- **Claude Code** with Python 3.9+ available (standard library only, nothing to `pip install`).
- **An Apify account and API token** (required). The skill uses two public Apify Store actors: `thenetaji/instagram-related-user-scraper` (expansion) and `datadoping/instagram-profile-scraper` (enrichment). Budget roughly $1-5 per run, plus ~£2 per 1,000 profiles when Apify does the enrichment.
- **A way for Claude to write Google Sheets**, ideally Composio's `GOOGLESHEETS_*` tools (via the Composio MCP or similar). The script itself only writes JSON; Claude builds the sheet from it.
- **Optional: your own creator-data API.** The skill was built against an in-house API that refreshes an Instagram profile and returns name, followers, bio, emails and region. If you have one, point the skill at it; if not, leave it unset and Apify does all the enrichment. The expected request and response shape is in `SKILL.md` under "Creator-data API".

## Environment variables

Put these in an env file, e.g. `~/.config/find-creators.env`, and `chmod 600` it:

```bash
APIFY_API_TOKEN=apify_api_xxxxxxxx           # required
# Optional, only if you have your own creator-data API:
CREATOR_API_BASE_URL=https://creators.youragency.com
CREATOR_API_TOKEN=xxxxxxxx
# CREATOR_API_REFRESH_PATH=/creators/instagram/{username}/refresh   # default shown
# Optional: email domains of creators already on your roster (they get dropped):
FIND_CREATORS_ROSTER_DOMAINS=youragency.com
```

## Install

```bash
mkdir -p ~/.claude/skills/find-creators
cp SKILL.md run.py filters.py README.md ~/.claude/skills/find-creators/
```

Then open `~/.claude/skills/find-creators/SKILL.md` and fill in the **Agency config** table at the top (agency name, env file path, default geo, the Google account sheets are created under, and so on). The rest of the skill refers to those placeholders.

Check it loads without calling any API:

```bash
python3 ~/.claude/skills/find-creators/run.py --help
```

## Use

In Claude Code:

```
/find-creators @examplecreator @anothercreator @thirdcreator
```

or just ask: "find UK fitness creators like @examplecreator and @anothercreator". Claude confirms the defaults, runs the pipeline (2-10 minutes), builds the sheet and returns the link with a short summary. Say "give me more" afterwards to append a deeper second pass to the same sheet.

## Tuning

- Defaults (geo, gender, verticals, follower range) are set in the config table and passed as flags; `run.py --help` lists every option.
- Add misses to `MANUAL_EXCLUDE` in `filters.py`, and big brand names in your niche to `BRAND_NAME_WORDS`.
- Full geo logic exists for `UK` and `US`. Other geographies need their own token lists in `filters.py`.
