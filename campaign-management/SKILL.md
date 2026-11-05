---
name: campaign-management
description: "Use when the user says /campaign-management, or asks to audit, chase or update creators on a live influencer campaign. Status-driven email management for an influencer marketing campaign: takes the latest creator CSV export from your campaign portal, audits each creator's email thread against their CSV status, and drafts the right next-stage email to close any gap. The Sent folder is canon for voice and copy. Drafts only, never sends."
user_invocable: true
trigger: "/campaign-management"
---

# Influencer Campaign Email Management

Status-driven audit and draft engine for a live influencer campaign: one brand, one product launch, a shortlist of creators moving through contract, content, brand approval, go-live and payment.

---

## Campaign config (fill in before first use)

Everything campaign-specific lives here. The rest of this skill refers to these placeholders. Update this block for each new campaign; leave the rest alone.

| Placeholder | What it is | Example |
|---|---|---|
| `{AGENCY}` | Your agency name | Acme Talent |
| `{SENDER_NAME}` | Name that signs the emails | Alex |
| `{SENDER_EMAIL}` | Mailbox the emails go out from | alex@youragency.com |
| `{GMAIL_ACCOUNT_ID}` | Connector account id for that mailbox (if your Gmail tool needs one) | gmail_xxxxx |
| `{BRAND}` | Brand name as it appears in subjects | Brand Co |
| `{CAMPAIGN}` | Short campaign name | Spring Launch |
| `{BRAND_HANDLE}` | Brand's social handle to tag | @brandco |
| `{HASHTAGS}` | Required hashtags | #AD #ProductName #BrandCo |
| `{PLATFORM}` | Content format | Instagram Reel |
| `{CURRENCY}` | Rate currency | GBP (£) |
| `{PAYOUT_COUNTRY}` | Bank details country | UK |
| `{PORTAL_ONE_CLICK}` | Creator one-click portal URL pattern | https://portal.youragency.com/review/{token}?pwd={password} |
| `{CSV_PATTERN}` | Filename of the portal's creator export | brandco-creators-YYYY-MM-DD.csv |
| `{SHORTLIST_CSV_PATTERN}` | Filename of the shortlist scoring file (has emails) | brandco-shortlist-YYYY-MM-DD-Ncreators.csv |
| `{BRAND_REVIEWER}` | Brand-side person who approves content (never named to creators) | the brand's content lead |
| `{BANNED_WORDS}` | Words or framings never to use in creator-facing copy | e.g. internal product names, "AI" |

---

## Core principle: status drives action, not inbox

The CSV is the source of truth for where each creator is in the campaign. For every creator:

1. Read their **CSV Status + Status Summary**.
2. Determine the email they SHOULD have last received from us at that stage.
3. Check their actual thread state.
4. If thread state doesn't match the CSV stage, draft the bridging email.

**Not** "what's new in the inbox, react to that." Reactive inbox-chasing misses the silent gaps: creators move forward through the portal without any email touch. A typical example is a creator who goes all the way to *Awaiting payment* without ever being told their revised content was approved. The audit catches that. The inbox scan does not.

---

## Inputs (required at runtime)

When `/campaign-management` is invoked, the user passes the path to the latest CSV export from the brand portal:

```
/campaign-management ~/Downloads/{CSV_PATTERN}
```

Or with a parenthesised duplicate-download suffix:

```
/campaign-management ~/Downloads/brandco-creators-YYYY-MM-DD (2).csv
```

**If no path is passed, ask for one.** Don't guess from filesystem listings: Downloads typically has several stale CSVs from earlier in the day.

---

## Source of voice: the Sent folder is canon

**Critical rule:** Drafts the skill writes are starting points. The version the sender actually sends (after tweaking it in Gmail) is the canonical voice for that stage. On every run, the skill must:

1. Read the latest sent example of each stage's email from `{SENDER_EMAIL}`'s Sent folder.
2. Use those as the voice/structure template for new drafts.
3. If the sender consistently changes the same phrase across multiple sends, surface it in the run report and update this SKILL.md's templates section.

When a draft and a sent email diverge, **the sent email wins**. Never argue from "the template". The sender's version is the ground truth.

---

## Access

### Gmail
Any Gmail connector works (Composio, a Gmail MCP, etc.). The action names below are Composio's; map them to your connector's equivalents.

- Mailbox: `{SENDER_EMAIL}` (account id `{GMAIL_ACCOUNT_ID}` if your connector needs one). Verify with `GMAIL_GET_PROFILE` at the start of every run.
- `search_threads`: paginate via `pageToken` until it comes back null.
- `get_thread`: read the full thread. Large threads may error with a "saved to disk" message; use Bash + `jq` to extract the last 3 to 6 messages without loading the whole file.
- `list_drafts`: check the current draft folder.
- `GMAIL_CREATE_EMAIL_DRAFT`: **required** for thread replies. Always pass the account, `thread_id`, and **leave `subject` empty** (setting a subject creates a new thread). Use `is_html: true`.
- `GMAIL_DELETE_DRAFT`: for stale draft removal. Never `GMAIL_UPDATE_DRAFT`; always delete + recreate.
- `GMAIL_GET_DRAFT`: for inspecting current draft bodies before deciding to replace.

### CSV (main campaign export)
- Read the path the user passes with the `Read` tool.
- Expected columns: `Creator Name, Instagram Handle, Instagram URL, Brand, Campaign, Status, Status Summary, Deliverables, Rate, Content Deadline, Go-Live Date, Creator Portal Link, Creator Portal Password, Creator One-Click Link, Brand Portal Link, Brand Portal Password`. Adjust to your portal's export.
- One row per creator on the shortlist (typically 20 to 30).
- **Note:** the main CSV usually does NOT include creator email addresses.

### Shortlist scoring CSV (secondary, only when emails are missing)
If new creators have been added to the campaign and their email isn't in any existing Gmail thread, ask the user for the shortlist scoring CSV (`{SHORTLIST_CSV_PATTERN}`). It has the `Email` column populated for every shortlisted creator. Match by social handle.

Source-of-truth precedence for emails:
1. Existing Gmail thread (most authoritative: that's the address they actually use).
2. Shortlist scoring CSV `Email` column.
3. Ask the user directly.

Never guess an email from a social handle (e.g. don't assume `@janedoe.com_` means `jane@janedoe.com`).

### Portal URLs (reference, not invoked here)
- Creator one-click: `{PORTAL_ONE_CLICK}` (auto-login via query string).
- Brand portal: separate token per creator.
- Agency-side dashboard for status changes.

---

## Campaign progression flow

| # | CSV Status | Status Summary phrase | Expected last email from us |
|---|------------|----------------------|------------------------------|
| 1 | **Awaiting** | "Hasn't accepted or declined yet" | Cold outreach, then form-fill ask, then shortlist email with one-click portal link |
| 2 | **Accepted** | "Accepted & signed contract, awaiting content submission" | Shortlist confirmation; chase if past content deadline |
| 3 | **Review** | "Content submitted, awaiting brand approval" | "Brilliant, content's landed our side, brand will review and come back via the portal" |
| 4 | **Amending** | "Brand requested changes, creator amending content" | "Brand have come back with these small tweaks..." (paraphrase brand feedback, never quote or name the brand reviewer) |
| 5 | **Live pending** | "Content approved, awaiting go-live post" | Green light + caption specs + portal URL drop instruction |
| 6 | **Bank pending** | "Content is live, awaiting bank details from creator" | Gentle nudge to add bank details in the portal IF silent for 24h+ after going live. Otherwise let the portal flow handle it. |
| 7 | **Awaiting payment** | "Bank details received, awaiting payment" | None required (portal handles it). Optionally a warm thanks if it closes the loop cleanly. |
| 8 | **Declined** | "Declined the campaign, reason: X" | Graceful close-out, keep the door open for future campaigns |
| 9 | **Voided** | "Campaign voided" | **DO NOT email.** Often a portal display bug (see Edge Cases). Verify the real status before sending anything. |

---

## Workflow

### Step 0: Preflight

1. **Verify the Gmail account.**
   ```
   GMAIL_GET_PROFILE (account: {GMAIL_ACCOUNT_ID})
   ```
   Confirm `emailAddress === {SENDER_EMAIL}`. If it's anything else, stop and ask the user to reconnect the right mailbox.

2. **Parse the CSV** (`Read` tool with the path passed).

3. **List current drafts** to know what's already queued.

4. **Pull the voice canon.** Search the Sent folder for recent campaign emails:
   ```
   search_threads({ query: "from:{SENDER_EMAIL} (subject:{CAMPAIGN} OR subject:'{BRAND}') newer_than:14d", pageSize: 50 })
   ```
   Paginate fully. For each thread, capture the latest message from the sender and tag it by detected stage (see "Stage detection" below). Use the LATEST sent example of each stage as the template.

### Step 1: Build the creator state table

From the CSV, build an in-memory table:

```
| Name | Handle | Email (from threads) | Status | Status Summary | Rate | Portal one-click |
```

The CSV doesn't include creator email, so emails come from the threads in Step 2.

### Step 2: Dispatch the status-audit sub-agent

**Mandatory:** do not run the audit in the main thread. Inbox scans are heavy and pagination must be exhaustive.

The sub-agent (general-purpose) receives:
- The CSV creator table
- The campaign progression flow (statuses to expected emails)
- The voice canon from Step 0 (latest sent example per stage)
- The current draft list

The sub-agent's task: for each creator, find their thread, identify the latest sent email from us, and decide:

- ✅ **MATCH**: thread state aligns with CSV status, no action.
- ⚠️ **GAP**: CSV status has moved past what the thread reflects. The creator needs a bridging email. Specify which stage email is needed.
- ⚠️ **STALE**: thread has moved beyond CSV status (e.g. creator clearly already went live but CSV still says Review). Surface as a CSV/portal correction request.
- ❌ **NO THREAD**: no email contact yet (new shortlist creators).
- ❌ **DRAFT IN FOLDER MISALIGNED**: a queued draft addresses an outdated state. Recommend delete + replace.

Sub-agent output format:

```
## Headline
{3-5 lines on biggest gaps + count of drafts needed}

## Per-creator matrix
| Creator | Status | Latest sent email | Alignment | Action |

## Drafts to create / replace
- {creator}: {stage}, {one-line rationale}, {thread_id}

## CSV/portal corrections (no email, flag to user)
- {creator}: {reason}

## Pagination receipts
```

The main thread then executes the drafts list.

### Step 3: Per gap, read the thread and write the draft

For each "Drafts to create" item from the sub-agent:

1. **Read the full thread** via `get_thread` (use `jq` extraction for large threads).
2. **Identify what the creator's last message actually said** if relevant. The bridging email is driven by the CSV stage, but if the creator asked something specific recently, address it in passing.
3. **Match the voice canon** for that stage. Mirror sentence shape, length, sign-off and caption-spec format from the sender's actual sent examples.
4. **Create the draft**:
   ```
   GMAIL_CREATE_EMAIL_DRAFT({
     account: "{GMAIL_ACCOUNT_ID}",
     thread_id: "<thread_id>",
     recipient_email: "<creator_email>",
     is_html: true,
     body: "<HTML body>"
     // NO subject: preserves threading
   })
   ```
5. **Verify the response.** Confirm the returned `threadId` equals the `thread_id` you passed. If they differ, the draft is orphaned; delete + recreate.

If multiple drafts are needed, batch them into one multi-execute call: parallel draft creation is fine. (Parallel *sending* is the problem; see Step 6.)

### Step 4: Replace stale drafts

For each "DRAFT IN FOLDER MISALIGNED" item:

1. Delete the stale draft.
2. Create the replacement.

Always delete + recreate, never update a draft in place.

### Step 5: Report

```
## /campaign-management run, {date}

### Headline
{1-2 sentence summary: how many drafts created, how many gaps closed, biggest correction}

### Drafts created/replaced ({n})
| Creator | Draft ID | Stage | Thread |

### CSV/portal corrections needed ({n})
| Creator | What's wrong | Fix needed |

### Cold outreach still pending
{list new Awaiting creators with no thread, and remind the user that emails are needed before drafting}

### Voice canon updates
{any Sent-folder phrasing changes detected vs the templates in this skill}

### Pagination receipts
{from sub-agent}
```

### Step 6: Send order (only after the user approves)

Drafts must be sent **one at a time**. Parallel sends tend to return false-failure errors ("Internal error" / "Precondition check failed") while the drafts stay queued, which then tempts a retry and produces duplicates.

---

## Email rules (never break)

- **HTML format always** (`is_html: true`).
- **No em dashes** anywhere. Use commas, full stops or colons.
- **British English** throughout (organise, colour, realise), or whatever house style your agency uses. Be consistent.
- **No CC on creator-side drafts.** The sender writes from `{SENDER_EMAIL}` directly. Never CC colleagues.
- **Empty subject on every reply draft.** Passing any subject (including `"Re: ..."`) creates a new thread instead of replying.
- **Never quote the brand reviewer's language verbatim, and never name them.** Paraphrase amend feedback. Brand-side reviewers can object strongly when their own bullet points are copied straight to creators.
- **Never use anything in `{BANNED_WORDS}`** in creator-facing copy.
- **Never push the agency's own sign-up, waitlist or other offers** in campaign follow-ups. These creators are already in.
- **Use the creator's actual country**, not "your geo" or "your area". Geo-decline drafts must name the specific country if known.
- **Short paragraphs.** One thought per line, generous spacing.
- **Sign-off:** `Best,<br>{SENDER_NAME}` on separate lines.
- **Never say "easiest thing".** It's never easiest for them.
- **Never anchor rates higher** than what the creator quoted.
- **Never offer calls** ("happy to jump on a call") unless the user has approved it for that draft.

---

## Caption specs (canonical phrasing)

Use the soft, inclusive phrasing. Creators respond better to "include these somewhere" than to a rigid format.

```html
<p>Quick caption specs to follow when you post (also in the portal), you can put them after your normal caption if you'd like:</p>
<ul>
  <li>Include <strong>"AD"</strong></li>
  <li>Tag <strong>{BRAND_HANDLE}</strong> somewhere in the caption</li>
  <li>Include hashtags: <strong>{HASHTAGS}</strong></li>
</ul>
<p>Once you've posted, drop the live {PLATFORM} URL into the portal. You'll then be prompted to fill in your {PAYOUT_COUNTRY} bank details so we can get you paid.</p>
```

NOT a hard-spec phrasing ("Open with AD..."). NOT em-dash-separated lists.

---

## Voice canon: templates by stage (refreshed from the Sent folder)

These are stub patterns. Real templates get refreshed each run from the sender's latest sent examples for each stage.

### Stage: Awaiting → Shortlist confirmation
Triggered when a creator makes the shortlist after submitting the application form.

```html
<p>Hey [Name],</p>
<p>Brilliant news, you've made the shortlist for the {CAMPAIGN} campaign at your [rate] form rate.</p>
<p>One-click into the campaign portal (contract, brief, content submission, brand approval and payment all in one):</p>
<p><a href="[ONE_CLICK_PORTAL_URL]">[ONE_CLICK_PORTAL_URL]</a></p>
<p>Works on any device, though we'd recommend a computer for the best experience.</p>
<p>Would love to lock you in for this one. Have a look and accept if you're keen, or if it's not for you no worries, just hit decline. Any questions, just shout.</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Accepted → Content chase (only if past deadline)
```html
<p>Hey [Name],</p>
<p>Just a quick nudge. You're all locked in contractually, brand are now keen to receive your content as we're heading into go-live.</p>
<p>The deadline was [original] but can flex to [new]. Sooner the better via the portal.</p>
<p>If something's come up and you can't make it work, just let me know and we'll regroup.</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Review → Content received ack
```html
<p>Hey [Name],</p>
<p>Brilliant, content's landed our side. Brand will review and come back via the portal with any feedback or sign-off shortly.</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Amending → Brand-requested tweaks
```html
<p>Hey [Name],</p>
<p>Quick one, brand have reviewed your content and just spotted [specific small thing, paraphrased, no reviewer name]. Could you [specific action]?</p>
<p>Once you've made the swap, re-upload via the portal and brand will sign off so you can go live.</p>
<p>Apologies for the back-and-forth!</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Live pending → Green light + caption specs
```html
<p>Hey [Name],</p>
<p>Brilliant news, brand have signed off on your content, you're free to go live whenever you're ready!</p>

[caption specs block, see "Caption specs" above]

<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Live pending after Amending → Green light post-amend
```html
<p>Hey [Name],</p>
<p>Brilliant news, brand have signed off on your revised content. You're free to go live whenever you're ready!</p>
<p>[Optional: one line acknowledging anything specific from their last message]</p>

[caption specs block]

<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Late-add shortlist (new creator added mid-campaign)
Same as the shortlist confirmation, sent as a fresh outbound email (no existing thread), but name the adjusted content deadline explicitly, e.g. "Content deadline is Monday [date] so you've got the working days for filming."

### Stage: Declined → Graceful close
```html
<p>Hey [Name],</p>
<p>Totally understand, thanks for letting me know. We'll keep you in mind for future campaigns that work for [country / their situation].</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Resubmission ack (creator confirms amends uploaded)
```html
<p>Hey [Name],</p>
<p>Brilliant, thanks for turning that around so quickly! I'll push it back to brand for final sign-off and ping you the moment we get the green light.</p>
<p>Best,<br>{SENDER_NAME}</p>
```

### Stage: Content submitted with a proposed caption
When a creator uploads content and proposes a caption in the same email, the reply must:
1. Acknowledge the upload.
2. Explain that brand reviews before go-live (don't auto-greenlight).
3. Flag any missing caption-spec elements (AD, `{BRAND_HANDLE}` tag, full hashtag set).

Never approve the caption silently.

### Stage: Talent manager asks about invoicing
Answer with "it's all via the portal, adding bank details unlocks payment". Don't offer email invoicing as a fallback.

---

## Stage detection (for parsing the Sent-folder voice canon)

Match the sender's sent emails to stages by keyword:

| Pattern in body | Stage |
|----------------|-------|
| "made the shortlist", "form rate", "One-click into the campaign portal" | Shortlist confirmation (Awaiting → Accepted) |
| "Just a quick nudge", "brand are now keen to receive your content" | Content chase (Accepted, past deadline) |
| "content's landed our side", "brand will review" | Content received ack (Review) |
| "a few small comments", "amend", "tweaks", "feedback" | Amend brief (Amending) |
| "given the green light", "free to go live", "caption specs" | Green light (Live pending) |
| "thanks for turning that around", "push it back to brand for final sign-off" | Resubmission ack |
| "hold off on posting", "couple of days" | Hold-off (temporary state, not a CSV status) |

---

## Golden rules (never break)

1. **Status drives action.** Never draft based on the inbox alone. Always check CSV status first.
2. **The CSV is the source of truth** for campaign state. If portal/CSV disagrees with the thread, flag the discrepancy, don't paper over it.
3. **The Sent folder is canon for voice.** The sender's tweaks win. Always.
4. **Never auto-send.** Drafts only. Even if the user casually says "send an email", create a draft and report the draft ID. Only send if the user explicitly confirms after review ("send this now" or equivalent) in the current turn.
5. **Never update a draft in place.** Always delete + recreate.
6. **Never quote or name the brand reviewer** in creator-facing copy.
7. **Never skip pagination** on inbox scans. The sub-agent must paginate fully.
8. **Never trust a "Voided" status without verification.** It's often a portal display bug.
9. **Never create a draft that says something already happened.** Check the Sent folder before drafting. If the green light went out yesterday, don't re-send it as a "follow-up".
10. **Never include side-asks in bridging drafts** while the creator is in active campaign flow. A side question from two days ago that the brand hasn't answered yet doesn't need a fresh email; it adds noise.
11. **Never email Voided creators** until you've confirmed the status is real, not a display bug.
12. **Always verify the Gmail account** at the start of every run.
13. **Always leave the subject empty** on reply drafts.
14. **Always pass the account id** on every Gmail call, if your connector takes one.
15. **Never trust a sub-agent's "sends didn't happen" claim without spot-checking it yourself.** If an audit concludes that previously drafted emails never went out, the main thread MUST read at least 3 of the specific threads before re-drafting anything. A wrong audit plus blind trust equals a batch of duplicate emails that ignore creators' actual replies. (See "Audit hallucination" below.)

---

## Edge cases (learned from live campaigns)

### "Voided" is usually a portal display bug
A creator marked Voided in the CSV may not actually be voided. A stale payout row in the database can shadow the real project state and surface as "Voided" in the brand portal. This has happened in practice: two creators showed Voided right after delivering their amends, and a portal fix flipped both back to Review.

Before drafting any close-out for a Voided creator:
1. Ask the user to hard-refresh the brand portal.
2. Wait for the corrected CSV.
3. Only then proceed.

If the user confirms the void is real (e.g. the brand explicitly pulled the creator), use the close-out template.

### CSV status lag
The CSV reflects the portal at export time, and the portal can lag behind reality. Two common patterns:
- **Live but still showing Review.** A talent manager confirms a creator has gone live with links, but the CSV still shows Review because the portal hasn't flipped them to Approved, so the URL-drop slot stays locked.
- **Declined by email, still Accepted in the portal.** A creator declines over email but the CSV shows Accepted for several days.

Surface these as "CSV/portal corrections needed" in the run report. Don't draft as if the CSV is wrong; flag it so the portal gets fixed, then re-run.

### Creators who skip the email stage
Some creators move forward entirely through the portal (accept, submit, go live, add bank details) without ever replying to email. Their thread state lags behind their CSV state. Catching these is the whole point of this skill. Typical case: a creator goes Amending → Approved → Live → Bank details in, all via the portal, while the last email from us was the amend request. They are owed a green-light email at minimum.

### Stale drafts when status moves
A draft created at stage N goes stale when the creator moves to stage N+1. Examples:
- A "soft amend" draft goes stale when the creator resubmits the same day.
- A "here's how to sort your stock issue" draft goes stale when the creator solves it themselves and submits content. Delete it and replace with a content-received ack.
- A "reassurance" draft goes stale when the brand approves the next revision.

Always re-check the draft folder before drafting. Drafts in the folder must reflect CURRENT status, not the status when they were written.

### Talent managers and agencies
Some creators are represented by a manager who handles comms for several of them. Address the manager directly, and frame updates per creator clearly (use bold sub-headers if covering more than one creator in one email).

### Cold outreach for new shortlist additions
Creators added mid-campaign need fresh outreach. The CSV won't include their emails: get them from the shortlist scoring CSV or ask the user. Don't look them up online or guess.

### Side-asks during active flow
If a creator asks a side question (e.g. "can you send me brand feedback for my portfolio?") while moving through the active flow, DO NOT create a separate "I'll come back to you on that" draft. It's noise. Either:
- Bake the answer into the next stage-driven email, OR
- Skip it, and pick it up after the campaign closes.

### Closer messages
When a creator's last message is a closer ("thanks, I'll post this afternoon!"), don't draft a one-line ack. It's noise. The campaign flow will catch up via the Awaiting payment status.

### Display bug pattern (Voided + payout state)
If several creators suddenly show the same unusual status (Voided, Stalled) at once, suspect a portal/database bug before drafting anything. Ask the user to hard-refresh and re-export.

### Audit hallucination: verify "sends didn't happen" claims
Real incident: an audit sub-agent ran several paginated Gmail searches and concluded "only 4 of Friday's 11 drafts went out." The main thread trusted it and drafted 10 replacement emails. **Every one was a duplicate** of a send that HAD gone out, and ignored the creators' replies in the meantime. It was only caught because the sender spotted their own already-sent green light, with the creator's follow-up question underneath, sitting below one of the "fresh" drafts.

**Root cause:** the sub-agent's pagination found the sends but mis-attributed them. The main thread took "0 outbound" at face value without checking a single thread.

**Hard process change:**
1. Whenever a sub-agent (or any audit step) concludes that previously tracked sends are missing from the Sent folder, the main thread MUST spot-check by reading at least 3 of the specific threads (`get_thread`, minimal format) before any re-draft.
2. If the check shows the sends DID happen, throw the audit away and do a fresh per-thread read.
3. The per-thread read is the source of truth. A sub-agent's summary is a hypothesis only.

**Pattern to recognise:** confident "many sends missing" claims with neat numbers ("7 of 11 drafts never sent") are MORE suspicious, not less. Aggregate audit failure tends to look like a clean, tidy answer.

### Draft-only, always
Live sends during follow-up work have led to the same person getting two update emails in one thread. Every Gmail action is draft-only unless the user has reviewed and approved that exact draft in the current turn.

---

## Learning loop

This skill should evolve as the sender gives feedback. The loop:

1. **The skill drafts an email.**
2. **The sender tweaks the draft in Gmail before sending.**
3. **The sent version becomes the canon** for that stage.
4. **The next run** scans the Sent folder and detects the new voice. If a phrase or structure changed consistently, surface it in the run report:
   ```
   ### Voice canon updates detected
   - Stage "Green light": the last 3 sent emails added a line about [X] that isn't in the template. Update SKILL.md?
   ```
5. **The user approves or rejects** the suggested update.
6. **If approved**, update the relevant template in this SKILL.md and append to the changelog.

### Append-only feedback log

Every time the user gives feedback that changes how the skill operates, append a line here (don't rewrite history):

```
- YYYY-MM-DD: {one-line summary of the rule/change added}
```

#### Changelog

- **v1** Status-driven framework: CSV status → expected email → thread match → draft the gap. Replaces reactive inbox-chasing.
- **v1** "Voided" treated as a probable portal display bug; no close-outs without a portal refresh.
- **v1** Sent folder is canon for voice and copy; drafts are starting points.
- **v1** Caption specs use the soft, inclusive phrasing only.
- **v1** No side-asks in bridging drafts.
- **v1** "Bank pending" stage added between Live pending and Awaiting payment.
- **v1** Shortlist scoring CSV added as the secondary source for creator emails.
- **v1** Late-add creators get the shortlist email with an explicit adjusted deadline.
- **v1** Hard rule: spot-check any audit claim that sends are missing before re-drafting.
- **v1** Content + proposed caption in one email: ack, explain brand review, flag missing caption elements.
- **v1** Manager invoice questions: everything via the portal.
- **v1** Draft-only rule reinforced after a live-send duplicate.

---

## What NOT to do

- Never react to the latest inbound and ignore CSV state.
- Never quote or name the brand reviewer in creator-facing copy.
- Never CC anyone on creator-side drafts.
- Never send emails: drafts only.
- Never create a draft that repeats what the last sent email already said.
- Never push the agency's own sign-up or waitlist in campaign follow-ups.
- Never offer to take rates by email if the campaign is form-only.
- Never trust a Voided status without verification.
- Never send drafts in parallel: one at a time only.
- Never update a draft in place: always delete + recreate.
- Never set a subject on reply drafts.
- Never email Awaiting creators without a confirmed email address (don't guess or look up).
- Never use em dashes.
- Never push deadlines or rates that anchor higher than what the creator quoted.
