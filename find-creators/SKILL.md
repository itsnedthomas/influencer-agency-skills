---
name: find-creators
description: "Given a few seed Instagram handles, run the full creator discovery pipeline: expand via related-users until there are enough candidates, enrich each profile (your own creator-data API if you have one, Apify otherwise), filter by vertical, gender, geography and email presence, rank, create a new Google Sheet, and return the URL. Use this whenever the user asks \"find creators for X\", \"/find-creators\", or provides seed creator handles and wants a ranked list for outreach."
user_invocable: true
trigger: "/find-creators"
---

# Find Creators

End-to-end creator discovery for `{AGENCY}` outreach campaigns. The hard-coded rules were learned on live campaigns and hardened over several more. Do NOT re-derive them: follow this playbook literally.

---

## Agency config (fill in before first use)

Everything agency-specific lives here. The rest of this skill refers to these placeholders. Fill this block in once; leave the rest alone.

| Placeholder | What it is | Example |
|---|---|---|
| `{AGENCY}` | Your agency name | Acme Talent |
| `{SKILL_DIR}` | Where this skill is installed | `~/.claude/skills/find-creators` |
| `{ENV_FILE}` | Env file holding the keys below (chmod 600) | `~/.config/find-creators.env` |
| `APIFY_API_TOKEN` | Env var: your agency's Apify team token (required) | `apify_api_xxxxx` |
| `CREATOR_API_BASE_URL` | Env var: base URL of your own creator-data API (optional, see "Creator-data API") | `https://creators.youragency.com` |
| `CREATOR_API_TOKEN` | Env var: bearer token for that API (optional) | `eyJhbGciOi...` |
| `CREATOR_API_REFRESH_PATH` | Env var: refresh endpoint path, `{username}` is substituted (optional) | `/creators/instagram/{username}/refresh` |
| `FIND_CREATORS_ROSTER_DOMAINS` | Env var: email domains of creators already on your roster, dropped from results (optional) | `youragency.com,talent.youragency.com` |
| `{DEFAULT_GEO}` | Default target geography | UK |
| `{DEFAULT_GENDER}` | Default creator gender | female |
| `{DEFAULT_VERTICALS}` | Default vertical buckets | `health,fitness,wellness,beauty-health` |
| `{DEFAULT_FOLLOWERS}` | Default follower range (sweet spot 3K-50K) | 3,000-700,000 |
| `{GOOGLE_ACCOUNT}` | Google account the sheet is created under | outreach@youragency.com |
| `{SHEETS_TOOL}` | How you reach Google Sheets | Composio `GOOGLESHEETS_*` tools, via the Composio MCP or a server-side Composio account |
| `{SHEET_TITLE}` | Sheet title pattern | `Creator Leads: <campaign name or date>` |
| `{STATE_DIR}` | Where per-campaign state files live | `/tmp` (use somewhere persistent if campaigns run for weeks) |
| `{APIFY_MONTHLY_CAP}` | Your Apify plan's monthly spend cap | $500/month |
| `{API_OWNER}` | Who to tell when the creator-data API is down | your platform engineer |

---

## When to trigger

- User runs `/find-creators` (slash command)
- User says "find creators for [campaign/niche]" and provides seed IG handles
- User provides 2+ IG profile URLs or handles and asks for a list / sheet / lookalikes

## Do NOT trigger when

- User just wants a single creator lookup (call your creator-data API or an Apify profile scraper directly)
- User wants competitor intel from Meta Ad Library (that's a separate pipeline: branded-content tags mostly surface brand-to-brand collabs, not micro-creators, so don't mix it in)

## What the user provides

**Required:**
- 2-10 seed IG handles (or profile URLs: extract the handle)

**Optional (ask only if campaign-critical, otherwise use defaults):**
- `target`: expansion **depth** knob (raw pool ≈ `target × 12`). Default **50**. This is NOT an output cap, see below.
- `vertical`: `health` | `fitness` | `wellness` | `beauty` | `beauty-health` | `hair` | `lifestyle` | `ugc` | `any` or custom comma-separated keywords. Default **`{DEFAULT_VERTICALS}`**.
- `gender`: `female` | `male` | `any`. Default **`{DEFAULT_GENDER}`**.
- `geo`: `UK` | `US` | `AU` | `any`. Default **`{DEFAULT_GEO}`**. (`UK` and `US` have full geo logic; `AU` is accepted but applies no geo filter or bonus yet.)
- `follower_min` / `follower_max`: range. Default **{DEFAULT_FOLLOWERS}** (sweet spot 3K-50K).

If the user is vague, don't pepper them with questions. Pick sensible defaults and say "going with {DEFAULT_GENDER} {DEFAULT_GEO} {DEFAULT_VERTICALS}, {DEFAULT_FOLLOWERS} followers. Tell me to change anything."

## Output is never capped: every qualified creator goes in the sheet

`run.py` writes **all** creators that pass the filters, ranked. There is no top-N truncation. `--target` only decides how deep to expand the raw candidate pool; it never throws qualifying creators away. (Learned on a live run: an earlier top-100 cut discarded ~500 already-paid-for qualified creators. Never do that. If you paid to scrape them, the user gets all of them.) A `--limit` flag exists only if someone explicitly asks for a hard cap; default is no cap.

## Pipeline (what the script does)

The heavy lifting is in `run.py`. Don't reimplement this: just call it. The script does:

1. **Expansion**: Apify `thenetaji/instagram-related-user-scraper` on the seeds (or, in `--more`, on the previous run's top keepers). Expands until the raw pool is `target × 12` deep (or 10 rounds).
2. **Enrichment (self-healing, cache-aware)**: your creator-data API (`POST {CREATOR_API_BASE_URL}{CREATOR_API_REFRESH_PATH}`) is primary when configured. `run.py` health-checks it first; if it's down, degraded or not configured, **Apify `datadoping/instagram-profile-scraper` automatically mops up** whatever the API couldn't do (chunked at 250 with `memory=1024`: a single big run OOMs at the 256MB default). Handles already enriched in the `--state` cache are never re-scraped or re-paid.
3. **Filter** (drops):
   - No email in dataset → drop
   - Email on a `FIND_CREATORS_ROSTER_DOMAINS` domain (already on your roster) → drop
   - Bio *positively confirmed* wrong region → drop (soft: absence of a geo mention is NOT a drop; unless `geo=any`)
   - Male name + bio signals → drop (unless `gender=any` or `male`)
   - Brand account → drop
   - No vertical keyword hit → drop
   - Already output in a prior run (via `--state`) → drop (never re-list anyone)
4. **Score**: vertical keywords, geo bonus (NYC/LA/UK etc.), micro-range bonus, personal-email bonus, agency-email penalty.
5. **Output**: **ALL** qualified creators as ranked JSON to `--out`, plus a `--state` update, and an Apify spend line on stdout.

### Sanity gate
If enrichment success drops below 10% (creator API AND Apify both failing), `run.py` **aborts with exit code 2** rather than write an empty sheet. The pool is saved to `--state` first, so a re-run after the outage clears costs nothing. If you see the abort, tell the user enrichment is down (and that `{API_OWNER}` may need to look at the creator API). Do NOT build a sheet.

## Your workflow when invoked

1. **Collect seeds.** If URLs: extract `username` from `https://instagram.com/<username>/`.
2. **Confirm params briefly.** Show what defaults you'll use, ask if they want changes.
3. **Run the pipeline.** ALWAYS pass a stable `--state` path per campaign: it caches enrichment and tracks who's already been output, so "give me more" later costs nothing on known handles and never re-lists anyone.
   ```bash
   set -a && source {ENV_FILE} && set +a
   python3 {SKILL_DIR}/run.py \
     --seeds <comma_separated_handles> \
     --target <N> \
     --vertical <keywords> \
     --gender <female|male|any> \
     --geo <UK|US|AU|any> \
     --follower-min <N> --follower-max <N> \
     --state {STATE_DIR}/find-creators-<campaign-slug>.state.json \
     --out /tmp/find-creators-$(date +%s).json
   ```
   Tail `stdout` for progress. Runs 2-10 minutes depending on depth. Exit code 2 = enrichment down (sanity gate): do not build a sheet.

   **"Give me more" / second pass**: reuse the SAME `--state`, add `--more`. It re-seeds expansion from the previous run's proven keepers (higher hit-rate), enriches only genuinely new handles, and appends only NEW qualifying creators with continued row numbering. Seeds are optional here.
   ```bash
   python3 {SKILL_DIR}/run.py --more \
     --gender female --geo US --vertical hair,beauty,lifestyle,fitness,health \
     --state {STATE_DIR}/find-creators-<campaign-slug>.state.json \
     --out /tmp/find-creators-more-$(date +%s).json
   ```
   The result JSON has `"append": true` and `"start_index": N`: append its rows to the existing sheet starting at that number, don't create a new sheet.

4. **Create a fresh Google Sheet** under `{GOOGLE_ACCOUNT}` via `{SHEETS_TOOL}` (`GOOGLESHEETS_CREATE_GOOGLE_SHEET1`). Title: `{SHEET_TITLE}`.

5. **Write 20-column header row** to `Sheet1!A1:T1` via `GOOGLESHEETS_BATCH_UPDATE` with values:
   ```
   ["#", "Handle", "First Name", "Full Name", "Primary Email", "Email Type",
    "All Emails", "Followers", "Engagement %", "Platform", "Profile URL",
    "Bio", "Region", "Source", "Source Brand/Seed", "Managed?",
    "Content Vertical", "Priority Score", "Status", "Notes"]
   ```

6. **Format header**: `GOOGLESHEETS_FORMAT_CELL` on `A1:T1`: `bold:true, red:0.88, green:0.96, blue:0.9, fontSize:11`. Then `GOOGLESHEETS_UPDATE_SHEET_PROPERTIES` with `frozenRowCount:1`. Then `GOOGLESHEETS_AUTO_RESIZE_DIMENSIONS` cols 0-20.

7. **Write rows**: load the JSON from `--out`, convert to 2D array, split into ~25-row chunks, write via `GOOGLESHEETS_BATCH_UPDATE` starting at `A2`. If the result JSON has `"append": true`, write starting at row `start_index + 1` on the existing sheet instead of creating a new one.

8. **Return** the sheet URL + a short summary (total creators, email split personal/business/mgmt, geo breakdown, top 5 standouts, and the Apify spend line from stdout).

### Sheet-building gotchas (save yourself the debugging)
- **A Google Sheets connector can die without warning.** If your usual route fails, any other transport that exposes the same `GOOGLESHEETS_*` tool slugs works the same way (for example a server-side Composio account called through a proxy tool): create → batch-update rows in 25-row chunks → format header → freeze row → conditional-format highlights → auto-resize. Same slugs, different transport.
- **Sheet/tab names are case-sensitive** in `BATCH_UPDATE` (`sheet_name`). It silently matched "All" → "ALL" once; always pass the exact casing you created.
- **Filtered/secondary tabs (e.g. a "NYC only" view) read the master by COLUMN POSITION.** If you build live `=FILTER(...)` tabs or conditional-format rules keyed to a column, then later **insert or delete a column on the master, every filter tab and highlight rule silently breaks** (shows `#N/A`, colours track the wrong column). If you add/remove master columns, re-point the filter formulas and CF rules. Don't offer live geo-split tabs unless the user asks: they're a maintenance liability, not a default.

## Lessons baked in: DO NOT REDISCOVER

These cost hours of debugging on live runs. The script already handles them, but if you're ever reimplementing or debugging, remember:

### Credentials
- Stored in `{ENV_FILE}` (chmod 600). Contains:
  - `APIFY_API_TOKEN`: your agency's **team** Apify account. Not whatever account your Apify MCP happens to be connected to: on a live run the MCP was on a different, personal account and hit its monthly limit mid-run.
  - `CREATOR_API_BASE_URL`, `CREATOR_API_TOKEN` (optional, only if you have a creator-data API)
  - `FIND_CREATORS_ROSTER_DOMAINS` (optional)
- Load with `set -a && source {ENV_FILE} && set +a`

### Creator-data API (optional, but cheaper and richer than Apify)
The pipeline was built against an in-house creator-data API. You don't need one: with `CREATOR_API_BASE_URL` unset, Apify's profile scraper does all the enrichment. If you have (or build) one, `run.py` needs exactly one endpoint:

- `POST {CREATOR_API_BASE_URL}{CREATOR_API_REFRESH_PATH}` with body `{"includePosts": false}` and `Authorization: Bearer {CREATOR_API_TOKEN}`
- Response: `{"creator": {"name", "followerCount", "bio", "emails": [...], "region", "isVerified", "externalUrl"}}`

Patterns from the API this was built against, worth copying if you design your own:
- `GET /creators/:platform/:username`: read cached
- `POST /creators/:platform/:username/refresh`: sync refresh (body: `{includePosts, postLimit}`). This is the workhorse.
- `POST /creators/:platform/:username/refresh-async`: queued rescrape (use when cached data is stale and `/refresh` returns cached)
- `GET /creators/:platform/:username/refresh-status`: poll job status
- `GET /creators/:platform/:username/related?offset=0&limit=20`: IG related profiles (limited, see below)
- Retire legacy endpoints outright rather than leaving them half-working.

### Cloudflare User-Agent gotcha
- If your API sits behind Cloudflare, it will block Python's default `urllib` / `requests` User-Agent with **HTTP 403 error code 1010**.
- **ALWAYS send a browser UA** on every request (`run.py` does):
  ```
  User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
  ```
- If enrichment returns 0 creators across the board, this is the likely cause: check the error body, not just `resp.get("creator")`.

### API outage + Apify enrichment fallback: AUTOMATIC IN run.py
- `run.py`'s `enrich_all()` is self-healing: it health-checks the creator API, and if it's down/degraded, Apify `datadoping/instagram-profile-scraper` mops up automatically. You should NOT need to hand-run anything. This section is background on *why* the fallback exists.
- On a live run the in-house API went fully down: every authenticated call returned HTTP 500, while bad tokens still got 401, so auth was fine and the backend was broken. If the run log shows `Creator API health check FAILED`, that's this. Mention that `{API_OWNER}` may want to look at it, but the run self-recovers via Apify.
- **Fallback specifics** (baked into `enrich_apify_datadoping`): input `{"usernames":[...]}`, returns `biography/followersCount/fullName/publicEmail/externalUrl`; combine `publicEmail` + regexed bio emails. Chunked at 250 with `?memory=1024&timeout=1800`, 3 in parallel: a single 1,451-username run OOM-died at the 256MB default (exit 137). Cost ~£2/1000 profiles. Slightly lower fidelity than a full creator API (no engagement/region) but covers the fields the filter needs.

### UK geo filter was leaking badly: fixed

A `--geo UK` run came back with ~40% of the "likely-UK" bucket actually based in
the US or Canada (San Diego, Toronto, Miami, Calgary, LA, Long Island), while
genuine UK creators (Cheshire, Worcester, South Yorks) sat in the same
unconfirmed bucket. Four separate root causes, all now fixed in `filters.py`:

1. **Whitespace.** `_geo_haystack()` now collapses all whitespace before token
   matching. IG bios are newline-heavy, so space-delimited tokens like `" uk "`
   and `" aus "` never matched when they sat at the end of a line. This alone
   caused both false negatives and false positives.
2. **`NON_UK_LOCATIONS` had drifted far behind `US_OTHER_TOKENS`.** `is_non_uk()`
   now reuses `NYC_TOKENS + LA_TOKENS + US_OTHER_TOKENS` directly instead of a
   hand-copied subset. Skips `US_TOKENS_UNSAFE_FOR_UK`: tokens like
   `charlotte`, `georgia`, `virginia`, `reading` double as British names/places
   and would bin real UK creators.
3. **Name + email were never checked.** `is_confirmed_uk()` / `is_non_uk()` now
   take `name` and `emails`. A `.co.uk` / `.uk` agency email is a strong UK
   signal (many UK creators state no city but route through a UK agency), and
   the location often lives in the display name only ("Toronto Makeup Artist"
   with a geo-free bio).
4. **Expat override.** "Scottish girly in Dubai" / "British living in Dubai" read
   as UK because nationality beat location. A stated `living/based in <place>`
   now wins over a nationality token.

Also: `is_male()` now scans the display name as well as the bio, and
`MALE_STRONG_MARKERS` makes a self-declaration decisive on its own. A profile
literally named "MALE MAKEUP ARTIST" was passing the `gender=female` filter
because a lone marker scored 2 against a threshold of 3.

Two-letter US state codes (`AZ |`, `AZ/LA`) are matched only against non-letter
boundaries, and `co`, `ms`, `al` are deliberately left out: `co` once binned a
real UK creator whose bio opened "Co Founder of @examplebranduk".

**The follower band is deliberately soft** (`follower_max * 3`), so a
`--follower-max 50000` run legitimately returns creators up to 150K and lets
scoring sort it out. If the user asks for a hard ceiling ("below 50K"), apply
the cut yourself on the output rows: don't assume the run honoured it.

### US geo mode
- `--geo US` fully works: soft bio tagging via `filters.us_geo_tag()` → NYC / LA / US / '' (empty = unconfirmed, NOT dropped). Only positively-confirmed non-US bios (London, Sydney, Toronto…) are dropped. NYC/LA +15 score, other-US +8.
- `hair` vertical bucket exists (haircare, curls, scalp…) with +5/hit (cap 10) bonus when requested.
- Sheet output: the Region column shows NYC/LA (highlight via conditional format `=$M2="NYC"` / `="LA"`). The preference on the US campaign this was built for was to label everything else Unknown rather than guess.

### `/related` endpoint limitations
If your creator-data API offers a "related profiles" endpoint, treat it as opportunistic only:
- Without a pool of logged-in IG accounts, `edge_related_profiles` is sparse/missing for most accounts when scraped logged-out.
- Even when populated, the "related" creators are what IG suggests to the logged-out scraper bot, not true graph neighbours.
- **For related-user discovery, use Apify `thenetaji/instagram-related-user-scraper` as primary** (that's what `run.py` does).

### Apify actor choice
- **Primary for expansion:** `thenetaji/instagram-related-user-scraper`: set `profileEnriched: false` (its enrichment is shallow) and `maxItem: 40`. Cost ~$0.004/result.
- **Enrichment: creator API first, `datadoping/instagram-profile-scraper` as the automatic fallback** (see the self-healing section above). Prefer your own API when you have one because it's effectively free per profile; datadoping only fires when the API can't. Never make datadoping the *default* enricher while a healthy API is configured.
- Do NOT use `apify/facebook-ads-scraper` for related-user discovery: it surfaces brand-to-brand collabs, not micro-creators.

### Concurrency
- `run.py` uses **48 concurrent creator-API threads** by default (`--creator-api-concurrency`), raised from an original 8 with no rate issues on the API it was built against. Lower it if yours rate-limits.
- But: ALWAYS log the actual HTTP error on failure. Don't do `resp.get("creator") or return None`: you'll silently drop every Cloudflare 403/HTTP 500 and waste hours debugging. (This is exactly how a live API outage first hid as "0 ok". The self-healing enricher, the error tally in the log and the sanity gate now catch it.)

### Filter defaults (baked into run.py / filters.py)
- **Gender detection:** first-name lookup against male/female sets + bio markers (`he/him`, `men's`, etc.), display name scanned too.
- **Non-UK:** bio/name contains "miami", "los angeles", "dubai", "melbourne", **"texas"** OR **"tx"** (as separator: `| TX ` etc.), "boston", "rio", a US state code, a non-UK country-code email domain, etc. AND no UK override.
- **Brand:** handle ends in `uk`, `official`, `hq`, `academy`, `store`, `worldwide`, `shop` OR bio contains "official channel", "world series of", OR name contains brand words (`hyrox`, `gymshark`, `official`, `academy`, `ltd`). Add the big brand names in your niche to `BRAND_NAME_WORDS`.
- **Roster:** any email on a `FIND_CREATORS_ROSTER_DOMAINS` domain drops the creator.
- **Vertical keyword buckets** (user-configurable, default `{DEFAULT_VERTICALS}`):
  - `health`: hormone health, wellness, holistic, nutrition, gut health, mindset, self care, healing, functional
  - `fitness`: hyrox, gym, pilates, athlete, strength, trainer, workout, running, marathon, yoga, glutes, lifting
  - `beauty-health`: glow, skincare, collagen, beauty from within, skin health, inside out
  - `beauty`, `hair`, `ugc`: see `VERTICAL_KEYWORDS` in `filters.py`
  - `lifestyle`: lifestyle, grwm, routine. **Use cautiously**: when lifestyle is requested without fitness, scoring flips into lifestyle mode (lifestyle is the strong bonus, pure fitness gets -5).

### Scoring weights (baked into filters.py)
```
+15  UK-confirmed (bio, name, region or .co.uk/.uk email)   [geo=UK]
+15  NYC or LA tag, +8 other US                             [geo=US]
+7   per health keyword (cap 21)
+6   per fitness keyword (cap 18)
+5   beauty-health keywords present
+5   per hair keyword (cap 10)                              [hair requested]
-3   pure fashion (no health/fitness signal)
+10  follower in sweet spot 3K-50K (micro)
+5   50K-150K (small-mid)
+2   150K-300K (mid)
-3   300K-700K (big)
-8   >700K (celeb tier)
-3   <3K (tiny)
+8   personal email
+3   business email (own domain)
-3   agency/mgmt email
+3   female first name confirmed
```

### Manual exclude list
Keep this fresh in `filters.py`: add any creator the user flags as a miss, one line each with the reason:
```
MANUAL_EXCLUDE = {
    "examplecreator",      # male creator, no bio gender markers
    "examplebrand.store",  # retail account, not a persona
}
```
For a one-off, `--exclude handle1,handle2` on the command line does the same without editing the file.

### Google Sheets header formatting reference
```
bg: (0.88, 0.96, 0.9)  # pale mint, not too bright
bold: true
font size: 11
freeze: row 1
tab color: (0.47, 0.78, 0.63)  # mint green accent
```

### Rate limit awareness
- Google Sheets: 60 reads/min, 60 writes/min. A fresh run is ~4-6 writes, safe.
- Apify: your plan cap is `{APIFY_MONTHLY_CAP}`. A full run costs $1-5, more if the creator API is down and Apify does all the enrichment (~£2/1000 profiles).
- Creator API: no hard limit was observed at concurrency 48 on the original; yours may differ.

## When the user asks to add a creator manually post-run

Just edit the sheet. Don't re-run the pipeline for 1-2 adds.

## When the user wants more / a second pass

Re-run `run.py` with `--more` and the **same `--state` path** used on the first run (see the workflow section). It expands from the previous run's proven keepers, reuses the enrichment cache (no re-scraping/re-paying for known handles), and appends only NEW qualifying creators with continued row numbering. The result JSON carries `"append": true` + `"start_index"`: append to the existing sheet, don't make a new one. Keep calling it to go deeper; the pool and the already-output set accumulate in `--state` forever.

## Failure modes and recovery

| Symptom | Cause | Fix |
|---|---|---|
| `run.py` exits code 2 "ABORT: enrichment success … below floor" | Creator API AND Apify both failing (sanity gate) | Do NOT build a sheet. Pool is cached in `--state`. Tell the user enrichment is down; re-run later (cache means no re-scrape). |
| `Creator API health check FAILED` in log but run continues | API down; Apify fallback took over automatically | None needed: self-healing. Mention `{API_OWNER}` may want to look at the API. |
| `No CREATOR_API_BASE_URL set` in log | No creator API configured | Expected if you don't have one. Apify does everything. |
| All creator-API refreshes fail silently | Cloudflare UA block | Verify the UA header is in the script; check the error tally for HTTP 403 |
| `/related` returns 0 total | IG graph doesn't expose it for that account (logged-out limit) | Use Apify related-users, which is what the script does |
| Apify actor "Monthly usage hard limit exceeded" | Wrong Apify account (MCP vs agency team token) | Ensure the run uses `APIFY_API_TOKEN` from `{ENV_FILE}`, not the Apify MCP tool |
| Filter tabs show `#N/A` after editing master | A column was inserted/deleted on the master sheet, breaking positional `=FILTER` refs | Re-point the filter formulas + conditional-format rules to the shifted column |
| Final sheet has males or brands | Filter miss | Flag to the user, drop manually, add to `MANUAL_EXCLUDE` or improve the first-name lists in `filters.py` for next time |

## Lineage

Built on a live UK women's health and wellness campaign. The original session produced:
- 522 candidates (7 UK seeds, 3 expansion rounds)
- 43 final creators matching the brief (women, UK, health/fitness/wellness, personal-email-heavy)

Later runs (a US hair-care campaign, UK fitness, UK beauty) added the US geo mode, the hair bucket, the self-healing enricher and the geo-leak fixes above.

## Files in this skill

- `SKILL.md`: this file
- `run.py`: the orchestrator (Apify + creator API + filter + rank + output JSON)
- `filters.py`: shared filter/scoring logic (imported by run.py)
- `README.md`: setup notes

Do not invoke individual modules directly; always call `run.py` with CLI args.
