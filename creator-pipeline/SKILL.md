---
name: creator-pipeline
description: "Use when the user says /creator-pipeline. Syncs creator email threads from Instantly cold campaigns into a Notion Creator Pipeline CRM. Cross-references the Gmail inbox that is CC'd on every cold outbound with the Instantly API (full thread, including auto sub-sequence replies that never reach the CC) so nothing falls through the cracks. Drafts contextual replies pushed towards each campaign's conversion goal. Drafts only, never sends."
user_invocable: true
trigger: "/creator-pipeline"
---

# Creator Pipeline CRM Sync + Draft Engine

On-demand sync between your agency Gmail inbox (`{SENDER_EMAIL}`, CC'd on every cold outbound) AND the Instantly API (full thread history, including auto sub-sequence replies that never reach the CC inbox). Updates statuses, actions and dates, creates new entries for untracked threads, and drafts replies dialled to each campaign's conversion goal.

Why this exists: Instantly's auto sub-sequences (step 2/3) often get replies that don't route to the CC. Without the Instantly API check, hundreds of warm replies sit invisible.

---

## Agency config (fill in before first use)

Everything agency-specific lives here. The rest of this skill refers to these placeholders. Fill this block in once; leave the rest alone. Per-campaign values (conversion goal, CTA link, reply flow) do NOT go here: they live in the Campaign Registry in Notion and are captured by Training Mode (Step 0.5).

| Placeholder | What it is | Example |
|---|---|---|
| `{AGENCY}` | Your agency name, as used in the handoff line | Acme Talent |
| `{SENDER_NAME}` | Name that signs every draft | Alex |
| `{SENDER_EMAIL}` | Inbox that is CC'd on every cold outbound and that drafts are written from | alex@youragency.co |
| `{GMAIL_ACCOUNT_ID}` | Connector account id for that mailbox (only if your Gmail tool needs one) | the account id your connector shows for that mailbox |
| `{SENDING_DOMAINS}` | Every domain your side sends from: main domain plus all Instantly cold-sending domains. Anything else counts as creator side | youragency.co, youragency-mail.com, tryyouragency.com, youragencytalent.co.uk |
| `{OUTBOUND_SENDERS}` | Names on the cold-sending accounts (used in the handoff line) | Sam, Jo |
| `{DEFAULT_OWNER}` | Owner value set on new CRM entries (the person this skill drafts as) | Alex |
| `{KNOWN_MGMT_DOMAINS}` | Talent management agency domains you've already seen reply for creators (creator-side proxies). Grows over time | sample-talent.co, examplemgmt.com |
| `{INSTANTLY_WORKSPACE}` | The Instantly workspace the cold campaigns run in | Acme Talent outbound |
| `{CREATOR_PIPELINE_DB_ID}` | Notion database id of the Creator Pipeline | 32-character id from the database URL |
| `{CREATOR_PIPELINE_DS_ID}` | Notion data source id of the Creator Pipeline | UUID from `notion-fetch` on the database |
| `{CAMPAIGN_REGISTRY_DB_ID}` | Notion database id of the Campaign Registry | 32-character id from the database URL |
| `{CAMPAIGN_REGISTRY_DS_ID}` | Notion data source id of the Campaign Registry | UUID from `notion-fetch` on the database |
| `{HUB_PAGE_URL}` | Optional Notion page that holds both databases | your Notion hub page link |
| `{GMAIL_LOOKBACK}` | How far back the Gmail sweep looks | 30d |

Per campaign (stored in the Campaign Registry, never hard-coded here):

| Placeholder | What it is | Example |
|---|---|---|
| `{CAMPAIGN_GOAL}` | What "converted" means on this campaign (Registry `Conversion Goal`) | "Creator fills in the application form", "Creator books a call", "Signed agreement returned" |
| `{CTA_LINK}` | Where the creator goes to convert (Registry `CTA Link`) | https://forms.youragency.co/apply, a booking link, a signing portal |

---

## Access

### Gmail
Any Gmail connector works (Composio, a Gmail MCP, etc.). The tool names below are generic: map each one to your connector's equivalent. If your MCP server prefixes tool names with an id, ignore the prefix and match on the action.

- `search_threads` / `search_messages`: search the inbox. Paginate until there is no next page token.
- `get_thread` / `read_thread`: read the full thread.
- `list_drafts`: check existing drafts.
- `create_draft` **with threading**: REQUIRED for replies. It must accept a `thread_id` and you leave the subject empty. Composio's `GMAIL_CREATE_EMAIL_DRAFT` does this. Hard-won lesson: some native Gmail MCP `create_draft` tools do NOT thread properly and strand the draft outside the conversation. Test once on a real thread; if the draft lands as a standalone email, don't use that tool for replies.
- Inbox: `{SENDER_EMAIL}` (account id `{GMAIL_ACCOUNT_ID}` if needed).

### Instantly (Composio, or the Instantly API directly)
Action names below are Composio's; map them if you call the API another way.

- `INSTANTLY_LIST_CAMPAIGNS`: discover active campaigns.
- `INSTANTLY_GET_CAMPAIGN`: pull campaign config + sequence copy (for training).
- `INSTANTLY_LIST_LEADS`: list leads in a campaign with reply/open/click status.
- `INSTANTLY_GET_LEAD`: full lead metadata by UUID.
- `INSTANTLY_LIST_EMAILS`: full thread history per lead (including auto sub-sequence replies).
- `INSTANTLY_SEARCH_CAMPAIGNS_BY_LEAD_EMAIL`: back-attribute a Gmail thread to a campaign.
- If the connection is inactive: reconnect it first (Composio: `COMPOSIO_MANAGE_CONNECTIONS`, toolkit = instantly). Make sure it points at `{INSTANTLY_WORKSPACE}`.

### Notion (Notion MCP)
- `notion-fetch`: read databases/pages.
- `notion-create-pages`: add entries.
- `notion-update-page`: update entries.
- `notion-search`: find entries by name.
- `notion-update-data-source`: schema changes (rare).

### CRM coordinates

**Creator Pipeline DB:**
- Database ID: `{CREATOR_PIPELINE_DB_ID}`
- Data Source ID: `{CREATOR_PIPELINE_DS_ID}`

**Campaign Registry DB:**
- Database ID: `{CAMPAIGN_REGISTRY_DB_ID}`
- Data Source ID: `{CAMPAIGN_REGISTRY_DS_ID}`

**Hub page:** `{HUB_PAGE_URL}`

---

## Creator Pipeline Schema

| Property | Type | Writable | Description |
|---|---|---|---|
| Creator | title | create only | Creator's first name (or full name if known) |
| Handle | text | handoff only | IG/TikTok handle (e.g. @example.creator) |
| Email | email | create only | Creator's email |
| Status | select | yes | Pipeline stage |
| Action | select | yes | Who needs to act |
| Source | select | create only | Where the lead came in |
| Owner | select | create only | Who's actively managing |
| Last Contact | date | yes | Most recent message date |
| Next Follow Up | date | yes | When the next nudge is due |
| Auto-Cadence Suppress | checkbox | yes | TRUE on Declined/Ghosted/Converted to stop further sequence sends |
| Conversion Goal | text | from campaign | Pulled from the Campaign Registry on create. Read-only thereafter |
| CTA Link | url | from campaign | Pulled from the Campaign Registry on create |
| Thread | url | create only | Gmail thread URL (use `https://mail.google.com/mail/u/0/#all/<threadId>`) |
| Campaign Name | text | create only | Human-readable campaign name |
| Instantly Campaign ID | text | create only | UUID, links back to the Campaign Registry |
| Instantly Lead ID | text | create only | UUID, for fetching the full thread via `INSTANTLY_GET_LEAD` |
| Notes | text | NEVER | Sacred, manually written |

### Status options (pipeline order)
1. **Sent**: outreach delivered, no reply yet
2. **Reply Received**: creator replied, intent unclear
3. **Engaged**: creator asking questions, in active dialogue
4. **Conversion Pending**: they're at the CTA step (form filling, signing, booking, etc.)
5. **Converted**: they completed the conversion goal
6. **Follow Up**: we sent last, 48h+ silent
7. **Ghosted**: N+ nudges with zero reply (auto-suppress)
8. **Declined**: explicit no

### Action options
- **Reply Required** (red): creator sent last
- **Waiting for Creator** (blue): we sent last
- **Waiting for Brand** (purple): we're blocked on brand-side info before we can reply
- **No Action** (default): terminal states (Converted, Declined, Ghosted)

---

## Campaign Registry Schema

| Property | Type | Description |
|---|---|---|
| Campaign Name | title | Human-readable name (e.g. "Brand Co x Retailer") |
| Instantly Campaign ID | text | UUID from Instantly |
| Status | select | Active / Paused / Closed / **Training Needed** |
| Conversion Goal | text | `{CAMPAIGN_GOAL}`: what "converted" looks like (e.g. "Creator fills in the application form to share rates") |
| CTA Link | url | `{CTA_LINK}`: the conversion endpoint (form, booking link, signing portal, etc.) |
| Subject Pattern | text | Regex/contains pattern to match Gmail threads (e.g. `[PAID].*Brand Co Campaign`) |
| Sending Account Pattern | text | Which of your sending accounts/domains sent the cold outbound (e.g. `sam@*`, `alex@*`) |
| Reply Flow | text | JSON-ish reply patterns. Example: `{"asks_budget": "Reply with rate range + form link", "agrees": "Send form link + briefing", "wants_more_info": "Send full brief link", "declines": "Warm close template", "follow_up": "Short friendly nudge + CTA link"}` |
| Sample Sequence Copy | text | First-step email body lifted from Instantly (context when drafting replies) |
| Last Trained | date | When the owner last reviewed/updated this campaign's flow |
| Notes | text | Manual context |

---

## Our sending domains (all count as "our side")

`{SENDING_DOMAINS}`

List every one: your main domain plus every cold-sending domain in Instantly. A missing domain makes your own follow-ups look like creator replies, which corrupts "who sent last" for every thread on it.

Anything else = creator side. Note: talent management agencies (e.g. `{KNOWN_MGMT_DOMAINS}`) are creator-side proxies: treat them as the creator's representative.

---

## Workflow

### Step 0: Sync Campaign Registry from Instantly

Pull all active Instantly campaigns and reconcile with the Registry.

```
INSTANTLY_LIST_CAMPAIGNS({ limit: 100 })
```

For each campaign returned:
1. Look up by `Instantly Campaign ID` in the Registry.
2. **If it exists and Status = Active**: skip (no training needed).
3. **If it exists and Status = Training Needed**: trigger the training flow (Step 0.5).
4. **If new (no Registry entry)**:
   - Pull `INSTANTLY_GET_CAMPAIGN({ id })` for the sequence copy.
   - Create a Registry entry with `Status = Training Needed`, `Sample Sequence Copy = <first email body>`.
   - Trigger the training flow (Step 0.5).

### Step 0.5: Training Mode (interactive: pause and ask the user)

When a campaign is `Training Needed`, the skill MUST pause and prompt the user with this exact format:

```
NEW CAMPAIGN DETECTED: <Campaign Name>

Sample sequence copy (Step 1):
> <first 5 lines of body>

I need to learn how to handle replies on this campaign before I draft anything.

Please answer:

1. **Conversion goal**: what does success look like for a creator on this campaign?
   (e.g. "fills in the application form", "books a call", "signed agreement returned")

2. **CTA link**: drop the URL we want them to click/fill (form, booking link, etc.)

3. **Reply flow**: walk me through the typical creator response patterns and what we say back. Cover at minimum:
   - They agree / show interest → ?
   - They ask for budget or rates → ?
   - They ask for more info / brief → ?
   - They decline / not a fit right now → ?
   - Their management agency replies on their behalf → ?
   - They go quiet after we've replied (follow-up nudge) → ?

4. **Subject pattern**: how can I detect Gmail threads belonging to this campaign?
   (e.g. exact subject line, contains "Brand Co Campaign", regex)

5. **Sending account pattern**: which of our sending accounts sent it? (e.g. `sam@*`)
```

After the user answers, write the responses to the Registry entry (`Conversion Goal` = `{CAMPAIGN_GOAL}`, `CTA Link` = `{CTA_LINK}`, `Reply Flow`, `Subject Pattern`, `Sending Account Pattern`, `Last Trained` = today) and flip Status to Active. Then resume processing.

If the user skips a question, leave the field empty in the Registry and skip drafts for matching threads (mark them `Reply Required (training incomplete)` in the report).

Never guess a campaign's conversion flow. An unknown campaign always means pause and ask.

### Step 1: Load Creator Pipeline State

```
notion-fetch({ id: "collection://{CREATOR_PIPELINE_DS_ID}" })
```

Build an in-memory map: email + Instantly Campaign ID → `{Status, Action, Last Contact, Page ID, Campaign ID, Owner, Auto-Cadence Suppress}`.

Paginate the data source until every row is loaded. A partial load means duplicate creates later.

### Step 2: Multi-Source Thread Discovery

**DEFAULT SCOPE RULE (set by the owner after early runs drowned in backlog):** Only process leads where the ball is in our court, i.e. the most recent message is from the creator/agency side and we haven't yet replied. Specifically:

- For each interested lead from Instantly, compare `timestamp_last_reply` (their reply) against `timestamp_last_contact` (our most recent send).
- **Only include the lead if `timestamp_last_reply > timestamp_last_contact`** (creator sent last, we haven't responded).
- Skip everything else by default: those are either "waiting for creator" or already terminal.

This keeps each run scoped to drafts the user actually needs to send, not the full backlog. Override only if the user explicitly asks for a "full sweep" or "all replies this week".

**Stale ball-in-court (>14 days old) auto-Ghosted:** Within the ball-in-court set, any lead whose `timestamp_last_reply` is more than 14 days old and which we never replied to gets auto-moved to **Ghosted** with `Auto-Cadence Suppress = TRUE` instead of being drafted to. The window for a warm reply has passed; replying now is awkward. Surface the count in the report so the user can override individual leads if needed.

Run BOTH sources, deduplicate by lead email:

**Gmail (the CC'd inbox):**

```
search_threads({ q: "to:{SENDER_EMAIL} OR cc:{SENDER_EMAIL} newer_than:{GMAIL_LOOKBACK}", maxResults: 100 })
```

**PAGINATE every search until there is no `nextPageToken`.** Stopping at page one silently drops older threads. Filter to threads matching one of the active campaigns' Subject Pattern (from the Registry). Skip noise (newsletters, internal team emails).

**Instantly (full thread history including auto sub-sequence replies):**

For EACH active campaign in the Registry:

```
INSTANTLY_LIST_LEADS({ campaign: "<campaign_id>", filter: "FILTER_LEAD_INTERESTED", limit: 100 })
INSTANTLY_LIST_LEADS({ campaign: "<campaign_id>", filter: "FILTER_VAL_CONTACTED", limit: 100 })
```

**Paginate via `next_starting_after`** until it comes back empty. Capture leads where `email_reply_count > 0` OR `status_summary.replied`.

For each replied lead:

```
INSTANTLY_LIST_EMAILS({ lead: "<lead_email>", limit: 50, sort_order: "asc" })
```

This is the AUTHORITATIVE thread because Instantly captures every step's reply, even the ones the CC missed.

**Cross-reference:** For each lead, check whether their email appears as a sender or recipient in any Gmail thread. If yes → use Gmail's threadId for drafting (so the reply lands in the right Gmail thread). If no Gmail thread exists → flag in the report ("Reply seen in Instantly only, no Gmail thread"); we may need to start a fresh Gmail message rather than reply (uncommon but real).

### Step 3: Smart Thread Processing

For EACH unique lead (keyed by email + campaign):

**Match to campaign:**
1. Use `Instantly Campaign ID` from `INSTANTLY_LIST_LEADS` directly when available.
2. If Gmail-only thread: match Subject Pattern from the Registry → infer campaign. If that fails, try `INSTANTLY_SEARCH_CAMPAIGNS_BY_LEAD_EMAIL`.
3. If nothing matches: flag for training (likely an unmapped campaign).

**If the lead matches an existing CRM entry (by email + Instantly Campaign ID):**
- **ALWAYS re-read** if Status ∈ {Reply Received, Engaged, Conversion Pending, Follow Up}. Never trust the CRM cache for active states: cached statuses go stale between runs and this was learned the hard way on a sibling pipeline.
- If Status = Sent, re-read only if Instantly shows a new reply event OR Gmail shows a newer message.
- If Status ∈ {Converted, Declined, Ghosted}: run a resurrection check. If the creator has new activity post-terminal, flag for un-terminal review.

**If new lead:** create an entry with all fields populated from Instantly metadata + the Registry's conversion goal.

### Step 4: Read & Analyse the Merged Thread

For each thread that needs processing:

1. **Pull both sources** (Gmail thread + Instantly emails for the lead).
2. **Merge chronologically** by timestamp. Dedupe by `Message-ID` header where possible.
3. **Filter out drafts** (Gmail labelIds includes "DRAFT"). A draft is never a sent message.
4. **Identify sides:** sender domain check against `{SENDING_DOMAINS}`.
5. **Find the latest creator-side sender:** the most recent non-our-side sender. If different from the CRM Handle/Creator name, treat it as a handoff (e.g. creator → management agency replies on their behalf). Update Handle/Creator only if the handoff is confirmed.
6. **Determine who sent last:** the last non-draft sender's domain.

### Step 5: Determine Status

Scan ALL non-draft messages chronologically. Apply the HIGHEST matching status:

**Converted (highest):**
- The campaign's CTA Link domain appears in Instantly events as `clicked`, or in any of our messages where the creator confirms completion.
- Creator's reply contains: "filled it out", "submitted", "done", "completed the form", "signed it", "booked".
- For form-based conversions: cross-check Instantly's `lead.status_summary.completed` if present.

**Conversion Pending:**
- We've sent the CTA Link in our most recent message AND the creator has not yet confirmed completion.

**Engaged:**
- Multi-message dialogue with creator-side replies asking questions ("what's the budget?", "which products?", "when's it filming?").

**Reply Received:**
- Exactly one creator reply, no further dialogue yet.

**Sent:**
- Zero creator replies (Instantly + Gmail).

**Follow Up:**
- We sent last, 48h+ silent on an active deal (Reply Received, Engaged, Conversion Pending).

**Ghosted:**
- We've sent 3+ messages with zero creator reply across 14+ days. Auto-set `Auto-Cadence Suppress = TRUE`.

**Declined:**
- Creator's last message contains: "not interested", "not a fit", "passing on this", "have to decline", "no thanks", "this isn't right". Auto-set `Auto-Cadence Suppress = TRUE` (except "Decline With Door Open", see Edge Cases).

### Critical Rules

- **Status moves backward ONLY when un-terminalising a wrongly archived entry** (creator re-engaged after Declined/Ghosted/Converted with new substantive activity).
- **Converted is not end of life.** A converted creator may still need follow-up communication: keep Action set appropriately even at Converted.
- **Conversion Goal in the CRM is read-only** after create. To change a campaign's conversion goal, edit the Registry entry, not the creator entry.

### Step 6: Determine Action

Based on the latest REAL (non-draft) message:
- Creator sent last AND Status not in {Converted, Declined, Ghosted} → **Reply Required**
- Our side sent last → **Waiting for Creator**
- Blocked on brand info → **Waiting for Brand**
- Terminal status → **No Action**

**Auto-fix:** Active entries with no Action chip → fix immediately based on who sent last.

### Step 7: Update or Create

**Existing entry: only update if something changed:**

```
notion-update-page({
  page_id: "<page_id>",
  command: "update_properties",
  properties: {
    "Status": "<new_status>",
    "Action": "<new_action>",
    "date:Last Contact:start": "YYYY-MM-DD",
    "date:Next Follow Up:start": "YYYY-MM-DD",
    "Auto-Cadence Suppress": "__YES__"  // only on Declined/Ghosted/Converted transitions
  }
})
```

**New entry:**

```
notion-create-pages({
  parent: { data_source_id: "{CREATOR_PIPELINE_DS_ID}" },
  pages: [{
    properties: {
      "Creator": "<first_name>",
      "Handle": "<@handle>",
      "Email": "<email>",
      "Status": "<status>",
      "Action": "<action>",
      "Source": "Instantly Campaign",
      "Owner": "{DEFAULT_OWNER}",  // default: this skill drafts as {SENDER_NAME} regardless of who sent the cold outbound
      "Conversion Goal": "<from Registry>",
      "CTA Link": "<from Registry>",
      "Campaign Name": "<from Registry>",
      "Instantly Campaign ID": "<UUID>",
      "Instantly Lead ID": "<UUID>",
      "Thread": "https://mail.google.com/mail/u/0/#all/<threadId>",
      "date:Last Contact:start": "YYYY-MM-DD"
    }
  }]
})
```

### Step 8: Draft Replies for Reply Required Entries

For each entry where `Action = Reply Required`:

1. **Skip if a draft already exists** for this thread (`list_drafts({ query: "subject:<thread_subject>" })` and check `threadId`). Never stack a second draft on a thread.
2. **Look up the campaign in the Registry** → load `Reply Flow` (JSON-ish patterns) + `CTA Link` + `Conversion Goal`.
3. **Match the creator's last message** to a Reply Flow pattern:
   - Keywords for `agrees` → use that pattern's response
   - Keywords for `asks_budget` → use the budget pattern
   - Keywords for `wants_more_info` → use the info pattern
   - Keywords for `declines` → use the decline pattern (warm close, set `Auto-Cadence Suppress = TRUE`)
   - Management agency reply → adapt to address the manager directly
4. **If no pattern matches confidently**: do NOT auto-draft. Flag in the report as `[NEEDS HUMAN: <email>]` so the user can write it, or tell the skill to learn this pattern (extends the Reply Flow for the next run).
5. **Draft with proper threading:**

```
create_draft({
  thread_id: "<thread_id>",     // CRITICAL: without this, the draft is standalone
  recipient_email: "<creator_email>",
  // NO CC: never CC colleagues or anyone else on creator-side drafts
  is_html: true,
  body: "<HTML body>"
  // DO NOT set subject: leaving it empty preserves threading
})
```

(Composio name: `GMAIL_CREATE_EMAIL_DRAFT`. Pass `{GMAIL_ACCOUNT_ID}` if your connector needs it.)

Body template: handoff line → contextual response (mapped to the Reply Flow) → CTA Link → sign-off.

**Handoff line (always, when the original outbound came from one of `{OUTBOUND_SENDERS}` rather than `{SENDER_NAME}`):**
> "Just jumping in here for <original sender's first name>, I'm {SENDER_NAME} from the {AGENCY} team."

(Use the first name on whichever sending account ran the original outbound. Never say that person is out of office.)

**Sign-off:**
```html
<br><br>Best,<br>{SENDER_NAME}
```

### Step 9: Follow-Up Logic

Entries where we sent last and 48h+ silent:
1. Move Status to `Follow Up`.
2. Set `Next Follow Up = today`.
3. `Action = Waiting for Creator`.
4. Draft a follow-up nudge using the Reply Flow's `follow_up` pattern from the Registry (if the campaign has no `follow_up` pattern, flag for human instead of improvising).

If the creator replies to a Follow Up entry: move Status to the correct active stage (Engaged or Conversion Pending depending on content) and set `Action = Reply Required`.

If 3+ nudges with zero reply across 14+ days → **Ghosted**, `Auto-Cadence Suppress = TRUE`, no further drafts.

### Step 10: Dedupe Pass (run at the end of every run)

After all updates, scan the full Creator Pipeline for duplicates:
1. Build a hash map: lowercased email + Instantly Campaign ID → list of page IDs. (Same email on different campaigns is expected and NOT a duplicate.)
2. Surface any group with 2+ page IDs.
3. **DO NOT auto-merge.** Output to the report's "Duplicate Creator Entries Detected" section. Recommend keeping the page with the most recent Last Contact + most populated Notes.

### Step 11: Report

Output a markdown summary:

```
## Creator Pipeline Sync Complete

### Campaign Registry State
| Campaign | Status | Conversion Goal | Active Leads | Replies This Run |

### Training Needed (X campaigns)
| Campaign | Why | Action |
For each campaign in `Training Needed` status, prompt the user for the training answers (Step 0.5).

### Updated (X entries)
| Creator | Handle | Campaign | Change |

### Un-Terminalised (recovered from wrongly archived)
| Creator | Old Status | New Status | Why |

### Created (X new entries)
| Creator | Handle | Campaign | Status | Action |

### Drafts Created (X)
| Creator | Campaign | Reply Flow Pattern | Thread |

### Reply Required: needs your attention
| Creator | Campaign | What they said | Draft? |

### Needs Human Reply (Reply Flow had no match)
| Creator | Campaign | Latest Message Snippet | Suggested Pattern To Add |

### Conversions This Run
| Creator | Campaign | CTA Completed |

### Follow-Ups Due
| Creator | Last Contact | Days Silent |

### Auto-Ghosted (stale ball-in-court, >14 days)
| Creator | Campaign | Their Last Reply |

### Auto-Cadence Suppressed (X newly muted)
| Creator | Reason (declined / ghosted / converted) |

### Instantly-Only Replies (no Gmail thread)
| Creator | Campaign | Suggested Next Step |

### Duplicate Creator Entries Detected
| Creator Email | Page IDs | Recommended Primary |

### Skipped (X unchanged)
Count only.

### Terminal (not touched)
Converted / Declined / Ghosted counts.
```

---

## Email Rules (NEVER break)

- **HTML format always** (`is_html: true`).
- **NO CC on creator-side drafts.** Never CC colleagues or anyone else. Drafts go directly to the creator/management agency only.
- **No em dashes anywhere.** Use commas, colons or full stops.
- **Short paragraphs**: one thought per line, generous spacing.
- **Drop CTA links directly** (no "click here", show the full URL).
- **Sign off:** "Best,<br>{SENDER_NAME}" (each on its own line, never together).
- **Handoff line:** "Just jumping in here for <original sender>, I'm {SENDER_NAME} from the {AGENCY} team." (swap in whoever's sending account ran the original outbound). Never say someone is out of office.
- **Reference the specific campaign** the creator was contacted about: it shows you read the thread.
- **Respect the creator's question**: if they asked a specific thing, answer it before pivoting to the CTA.
- **Push to the CTA every reply**: that's the conversion goal (`{CAMPAIGN_GOAL}`). Soft sell, but always there.
- **Voice:** casual, warm, direct, plain English, no corporate speak. Match the spelling convention of your market (e.g. British spelling for UK creators).

---

## Golden Rules (NEVER BREAK)

1. **NEVER modify Notes**: sacred, manually written.
2. **NEVER auto-send**: drafts only.
3. **NEVER draft without a matching Reply Flow pattern**: flag for a human instead.
4. **NEVER move Status backward** EXCEPT via the un-terminal exception (post-terminal new activity).
5. **NEVER trust the CRM cache for active statuses**: always re-read Reply Received / Engaged / Conversion Pending / Follow Up threads.
6. **NEVER skip the Instantly API check**: a Gmail-only sweep misses auto sub-sequence replies.
7. **ALWAYS set `Auto-Cadence Suppress = TRUE`** on Declined / Ghosted / Converted transitions (sole exception: Decline With Door Open).
8. **ALWAYS use a threading-capable draft tool** (`thread_id` set, subject empty). A draft tool that doesn't thread strands the reply outside the conversation.
9. **ALWAYS pause and ask** when an unknown campaign is detected: never guess a conversion flow.
10. **ALWAYS dedupe at the end of every run.**
11. **NEVER change Owner, Source, Email, Thread, Notes, Conversion Goal, or CTA Link after create.** Handle and Creator may be updated only on a confirmed handoff.
12. **NEVER count drafts as sent**: filter labelIds for "DRAFT".
13. **ALWAYS paginate** Gmail (`nextPageToken`), Instantly (`next_starting_after`) and Notion until exhausted. Page one is never the whole picture.

---

## Edge Cases

### Auto sub-sequence replies (the core failure mode this skill solves)
When Instantly sends step 2 or step 3 of a sequence, the reply often goes back to that sending account WITHOUT CC'ing `{SENDER_EMAIL}`. The reply lives only in Instantly's UI / API. **Always check `INSTANTLY_LIST_EMAILS` per lead**: never assume Gmail has the full picture.

### Management agency handoffs
A creator's manager replies on their behalf (e.g. `manager@sample-talent.co` replying for a creator you emailed directly). Treat the manager as the creator's representative: update the Creator (contact) name to the manager but keep Email as the original creator's. Add a line to Notes only if Notes is empty. Add the manager's domain to `{KNOWN_MGMT_DOMAINS}` so future runs recognise it.

### Creator asks for more money than budget
Don't auto-decline. Flag as `Engaged` + `Reply Required` and surface it in the report: rate negotiations are handled manually by the owner.

### Out-of-office auto-replies
Keep the current Status. Set Next Follow Up to the return date mentioned. Action = `Waiting for Creator`. Don't trigger a Ghosted decision based on out-of-office silence.

### "Yes please, send more info" replies
The biggest conversion lever. Always draft a reply that includes:
1. Brief acknowledgement
2. Direct answer to whatever they asked
3. The CTA Link from the Registry
4. Soft close ("any questions, let me know")

### Decline with door open
"Not for this one but keep me in mind" → set Status = Declined for THIS campaign, but DO NOT set Auto-Cadence Suppress = TRUE (we want them in future campaigns). This is the only Decline transition where suppress stays FALSE.

### Multiple campaigns, same creator
Same email contacted on 2+ campaigns → 2+ separate Creator Pipeline entries (one per campaign). Match by `email + Instantly Campaign ID`, not just email.

### Stale leads (Sent 30+ days ago, never replied)
Move to Ghosted, set Auto-Cadence Suppress, drop from active processing.

---

## What NOT to Do

- Never auto-send: drafts only, always.
- Never draft without a Reply Flow match: surface it to the user for the missing pattern instead.
- Never modify Notes.
- Never delete entries (mark Ghosted/Declined/Converted with Suppress = TRUE).
- Never assume a campaign's conversion goal: ask via Step 0.5 training mode.
- Never use a draft tool that doesn't thread for replies: it strands the draft outside the thread.
- Never query Instantly without the connection active: reconnect first if needed.
- Never CC anyone on a creator-side draft.

---

## First-Run Checklist

When `/creator-pipeline` runs for the first time:

1. Check the Agency config table is filled in (domains, inbox, Notion ids). Stop and ask if any required value is still a placeholder.
2. Pull `INSTANTLY_LIST_CAMPAIGNS`: every Active campaign will be `Training Needed` in the Registry.
3. For each, run training mode (Step 0.5): the user answers the 5 questions per campaign. About 2 minutes per campaign.
4. Once trained, the skill processes the full inbox + Instantly history end to end.
5. Subsequent runs only re-train when a NEW campaign appears or the user manually flips an existing campaign back to `Training Needed` to update its Reply Flow.

This means the first run is heavy (training) but every subsequent run is fast.
