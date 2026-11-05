#!/usr/bin/env python3
"""
find-creators: end-to-end pipeline.

Pipeline:
  1. Expansion: Apify related-user-scraper on seeds (or, in --more mode, on the
     previous run's top keepers) until the raw pool is deep enough.
  2. Enrichment (self-healing): your own creator-data API first, if you have one
     configured and it passes a health check; Apify's datadoping profile-scraper
     then mops up whatever is still missing (or does the lot if you have no
     creator API). Already-enriched candidates from a prior run's cache are
     NEVER re-paid.
  3. Filter (has email, gender, geo, brand, vertical): all soft geo, no hard
     keyword exclusions beyond a positively-confirmed wrong region.
  4. Score + rank.
  5. Write EVERY qualified creator to --out (no top-N cap by default).

Key design notes:
  * Output is NOT capped. Every creator that passes the filters goes in the sheet.
    --target only controls how DEEP to expand (raw pool size), never truncation.
  * --state <path> persists the full enriched pool + the set of already-output
    handles. Re-running with the same --state reuses the cache (no re-scraping,
    no re-paying) and never re-outputs anyone. --more re-seeds expansion from the
    proven keepers and appends only NEW qualifying creators.

Usage (fresh run):
  python3 run.py --seeds handle1,handle2,handle3 \\
    --target 50 --vertical health,fitness,wellness,beauty-health \\
    --gender female --geo UK --follower-min 3000 --follower-max 700000 \\
    --state /tmp/fc-<campaign>.state.json --out /tmp/fc_result.json

Usage (give me more: appends, reuses cache, no re-scrape cost on known handles):
  python3 run.py --more --geo US --gender female \\
    --vertical hair,beauty,lifestyle,fitness,health \\
    --state /tmp/fc-<campaign>.state.json --out /tmp/fc_more.json

Environment (load from your env file, e.g. ~/.config/find-creators.env):
  APIFY_API_TOKEN               required
  CREATOR_API_BASE_URL          optional: your own creator-data API
  CREATOR_API_TOKEN             optional: bearer token for that API
  CREATOR_API_REFRESH_PATH      optional: default /creators/instagram/{username}/refresh
  FIND_CREATORS_ROSTER_DOMAINS  optional: your roster email domains (read by filters.py)
"""
import argparse
import datetime
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

# Make filters.py importable whether run from anywhere
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import filters as F

# Browser User-Agent on every creator-API call: APIs behind Cloudflare block
# Python's default urllib/requests UA with HTTP 403 (error code 1010).
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


DEFAULT_REFRESH_PATH = "/creators/instagram/{username}/refresh"


def creator_api_headers(token):
    h = {"Content-Type": "application/json", "User-Agent": UA}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def apify_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def log(msg):
    print(msg, flush=True)


def extract_handle(s):
    """Extract IG username from URL, @handle, or raw handle."""
    s = s.strip().lstrip("@")
    m = re.search(r"instagram\.com/([A-Za-z0-9_.]{2,30})", s)
    if m:
        return m.group(1).lower()
    return re.sub(r"[^A-Za-z0-9_.]", "", s).lower()


# ---------------------------------------------------------------------------
# Apify low-level helpers
# ---------------------------------------------------------------------------
def _apify_get(token, path):
    req = urllib.request.Request(
        f"https://api.apify.com/v2{path}{'&' if '?' in path else '?'}token={token}",
        headers={"Content-Type": "application/json"}, method="GET",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _apify_post(token, path, body):
    req = urllib.request.Request(
        f"https://api.apify.com/v2{path}{'&' if '?' in path else '?'}token={token}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def _apify_dataset_items(token, ds_id):
    items, offset = [], 0
    while True:
        batch = _apify_get(token, f"/datasets/{ds_id}/items?format=json&clean=true&offset={offset}&limit=1000")
        if not batch:
            break
        items.extend(batch)
        offset += len(batch)
        if len(batch) < 1000:
            break
    return items


def apify_spend_since(token, start_iso):
    """Best-effort: sum usageTotalUsd for Apify runs started at/after start_iso."""
    try:
        data = _apify_get(token, "/actor-runs?limit=100&desc=true")
        total = 0.0
        for r in (data.get("data", {}).get("items") or []):
            if (r.get("startedAt") or "") >= start_iso:
                total += r.get("usageTotalUsd") or 0.0
        return total
    except Exception as e:
        log(f"  (cost lookup failed: {type(e).__name__})")
        return None


# ---------------------------------------------------------------------------
# Expansion (Apify related-user-scraper)
# ---------------------------------------------------------------------------
def apify_related_users(token, usernames, max_per_seed=40, timeout=700):
    """Call thenetaji/instagram-related-user-scraper synchronously.
    Returns list of records with at least 'username' field."""
    body = {
        "username": list(usernames),
        "profileEnriched": False,  # shallow; we enrich via the creator API / Apify profile-scraper instead
        "maxItem": max_per_seed,
        "type": "similar_users",
    }
    req = urllib.request.Request(
        f"https://api.apify.com/v2/acts/thenetaji~instagram-related-user-scraper/run-sync-get-dataset-items?timeout={timeout}",
        data=json.dumps(body).encode(),
        headers=apify_headers(token),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout + 30) as r:
            data = json.loads(r.read().decode())
            return data if isinstance(data, list) else []
    except Exception as e:
        log(f"  Apify error: {type(e).__name__} {str(e)[:150]}")
        return []


def _merge_related(candidates, r):
    """Merge one related-user record into candidates. Returns handle if NEW."""
    h = extract_handle(r.get("username") or "")
    if not h:
        return None
    if h in candidates:
        seed = r.get("seedUsername") or r.get("originUsername") or ""
        if seed:
            s_list = set(candidates[h].get("seed_sources") or [])
            s_list.add(seed)
            candidates[h]["seed_sources"] = sorted(s_list)
        return None
    candidates[h] = {
        "username": h,
        "name": r.get("fullName") or r.get("name"),
        "bio": r.get("biography") or r.get("bio"),
        "enriched": False,
        "seed_sources": [r.get("seedUsername") or r.get("originUsername") or ""],
        "sources": ["apify_related"],
    }
    return h


def expand(seeds, apify_token, target_raw, max_rounds=10, batch_size=8, candidates=None):
    """Iteratively expand seeds via Apify related-users until pool >= target_raw
    or rounds/handles are exhausted. Merges into `candidates` if supplied."""
    if candidates is None:
        candidates = {}
    for s in seeds:
        candidates.setdefault(s, {
            "username": s, "seed_sources": ["SEED"],
            "sources": ["user_manual"], "enriched": False,
        })
    expanded_from = set()

    for round_i in range(1, max_rounds + 1):
        if len(candidates) >= target_raw:
            log(f"  Round {round_i}: raw pool {len(candidates)} >= {target_raw}, stopping.")
            break
        unexpanded = [h for h in candidates if h not in expanded_from and not candidates[h].get("enriched")][:batch_size]
        if not unexpanded:
            unexpanded = [h for h in candidates if h not in expanded_from][:batch_size]
        if not unexpanded:
            log(f"  Round {round_i}: no more handles to expand, stopping.")
            break
        log(f"  Round {round_i}: expanding {len(unexpanded)} -> {unexpanded[:3]}{'...' if len(unexpanded) > 3 else ''}")
        related = apify_related_users(apify_token, unexpanded, max_per_seed=40)
        new_count = sum(1 for r in related if _merge_related(candidates, r))
        expanded_from.update(unexpanded)
        log(f"  Round {round_i}: +{new_count} new, total {len(candidates)}")
    return candidates


def expand_from(sources, candidates, apify_token, per_chunk=16, parallel=3, max_per_seed=40):
    """Targeted expansion: run related-users on the given source handles in
    parallel chunks, merge NEW handles into candidates. Returns new handles."""
    chunks = [sources[i:i + per_chunk] for i in range(0, len(sources), per_chunk)]
    related = []
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(apify_related_users, apify_token, ch, max_per_seed) for ch in chunks]
        for f in as_completed(futs):
            related.extend(f.result())
    new_handles = [h for h in (_merge_related(candidates, r) for r in related) if h]
    return new_handles


# ---------------------------------------------------------------------------
# Enrichment (self-healing: creator API primary, Apify profile-scraper fallback)
# ---------------------------------------------------------------------------
def creator_api_refresh(base, token, username, timeout=45):
    """POST {base}{CREATOR_API_REFRESH_PATH} -> (username, creator|None, err|None).

    Expected response: {"creator": {"name", "followerCount", "bio", "emails",
    "region", "isVerified", "externalUrl"}}. Errors are returned, never
    swallowed, so a Cloudflare 403 or a backend 500 is visible in the log."""
    path = os.environ.get("CREATOR_API_REFRESH_PATH") or DEFAULT_REFRESH_PATH
    req = urllib.request.Request(
        base.rstrip("/") + path.format(username=username),
        data=json.dumps({"includePosts": False}).encode(),
        headers=creator_api_headers(token),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
            return username, d.get("creator"), None
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode(errors="replace")[:200]
        except Exception:
            pass
        return username, None, f"HTTP {e.code} {body}"
    except Exception as e:
        return username, None, f"{type(e).__name__}: {str(e)[:150]}"


def creator_api_alive(base, token, sample_handles):
    """Health-check the creator API on up to 3 handles. True if any returns a creator."""
    for h in sample_handles[:3]:
        _, creator, err = creator_api_refresh(base, token, h)
        if creator:
            return True
        if err:
            log(f"    creator API health check @{h}: {err}")
    return False


def _merge_creator_api(candidates, h, creator):
    candidates[h].update({
        "name": creator.get("name") or candidates[h].get("name"),
        "followerCount": creator.get("followerCount"),
        "bio": creator.get("bio") or candidates[h].get("bio"),
        "emails": creator.get("emails") or [],
        "region": creator.get("region"),
        "isVerified": creator.get("isVerified"),
        "externalUrl": creator.get("externalUrl") or creator.get("external_url") or creator.get("website"),
        "enriched": True,
    })


def enrich_creator_api(candidates, handles, api_base, api_token, concurrency=48):
    ok, errors = 0, {}
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = {ex.submit(creator_api_refresh, api_base, api_token, h): h for h in handles}
        for i, fut in enumerate(as_completed(futures), 1):
            h, creator, err = fut.result()
            if creator:
                _merge_creator_api(candidates, h, creator)
                ok += 1
            elif err:
                key = err[:40]
                errors[key] = errors.get(key, 0) + 1
            if i % 100 == 0:
                log(f"    creator API {i}/{len(handles)} ({ok} ok)")
    if errors:
        top = sorted(errors.items(), key=lambda kv: -kv[1])[:3]
        log(f"    creator API errors (top): {top}")
    return ok


def enrich_apify_datadoping(candidates, handles, token, chunk=250, memory=1024, parallel=3):
    """OOM-safe fallback via datadoping/instagram-profile-scraper.
    A single big run OOMs at the 256MB default, so chunk (~250) with 1GB and
    run a few in parallel. Merges bio/followers/name/publicEmail + bio-regex emails."""
    def run_chunk(idx, users):
        run = _apify_post(token, f"/acts/datadoping~instagram-profile-scraper/runs?memory={memory}&timeout=1800",
                          {"usernames": users})
        run_id = run["data"]["id"]
        log(f"    apify-enrich chunk {idx}: run {run_id} ({len(users)} handles)")
        for _ in range(160):  # up to ~40 min
            time.sleep(15)
            d = _apify_get(token, f"/actor-runs/{run_id}")["data"]
            if d["status"] in ("SUCCEEDED", "FAILED", "ABORTED", "TIMED-OUT"):
                items = _apify_dataset_items(token, d["defaultDatasetId"])
                log(f"    apify-enrich chunk {idx}: {d['status']} ({len(items)} items)")
                return items
        return []

    chunks = [handles[i:i + chunk] for i in range(0, len(handles), chunk)]
    items = []
    with ThreadPoolExecutor(max_workers=parallel) as ex:
        futs = [ex.submit(run_chunk, i, ch) for i, ch in enumerate(chunks, 1)]
        for f in as_completed(futs):
            items.extend(f.result())

    ok = 0
    for it in items:
        h = (it.get("username") or "").lower()
        if h not in candidates:
            continue
        bio = it.get("biography") or ""
        emails = set(EMAIL_RE.findall(bio))
        if it.get("publicEmail"):
            emails.add(it["publicEmail"].strip())
        candidates[h].update({
            "name": it.get("fullName") or candidates[h].get("name"),
            "bio": bio or candidates[h].get("bio"),
            "followerCount": it.get("followersCount"),
            "emails": sorted(e.lower() for e in emails),
            "externalUrl": it.get("externalUrl") or candidates[h].get("externalUrl"),
            "enriched": True,
        })
        ok += 1
    return ok


def enrich_all(candidates, api_base, api_token, apify_token=None, concurrency=48):
    """Self-healing, cache-aware. Only enrich handles not already enriched.
    Creator API first (if configured and the health check passes); Apify
    datadoping then mops up everything the API couldn't do, whether it is fully
    down, degraded, not configured, or just missed a handle.
    Returns (enriched_count, attempted_count)."""
    todo = [h for h, c in candidates.items() if not c.get("enriched")]
    if not todo:
        log("  Enrichment: whole pool already enriched (cache hit), nothing to pay for.")
        return 0, 0

    if not api_base:
        log("  No CREATOR_API_BASE_URL set -> enriching everything via Apify profile-scraper")
    elif creator_api_alive(api_base, api_token, todo):
        log(f"  Creator API health check OK -> enriching {len(todo)} via creator API (concurrency {concurrency})")
        enrich_creator_api(candidates, todo, api_base, api_token, concurrency=concurrency)
    else:
        log("  Creator API health check FAILED (down/500/403) -> skipping it, going straight to Apify fallback")

    missing = [h for h in todo if not candidates[h].get("enriched")]
    if missing and apify_token:
        log(f"  Apify datadoping fallback enriching {len(missing)} remaining handles")
        enrich_apify_datadoping(candidates, missing, apify_token)
    elif missing:
        log(f"  WARNING: {len(missing)} handles left unenriched and no Apify token to fall back on")

    enriched = sum(1 for h in todo if candidates[h].get("enriched"))
    log(f"  Enrichment complete: {enriched}/{len(todo)} enriched this run")
    return enriched, len(todo)


# ---------------------------------------------------------------------------
# Filter + score + rank
# ---------------------------------------------------------------------------
def apply_filters(candidates, requested_verticals, gender, geo, follower_min, follower_max, extra_exclude=None):
    kept = []
    drops = {"no-email": 0, "non-geo": 0, "male": 0, "female-required-male-detected": 0,
             "brand": 0, "no-vertical": 0, "out-of-range": 0, "manual": 0, "on-roster": 0}
    extra_exclude = set(extra_exclude or [])
    roster_domains = getattr(F, "ROSTER_EMAIL_DOMAINS", set())

    for h, c in candidates.items():
        if h in F.MANUAL_EXCLUDE or h in extra_exclude:
            drops["manual"] += 1
            continue
        emails = c.get("emails") or []
        if not emails:
            drops["no-email"] += 1
            continue
        if roster_domains and any(e.split("@")[-1].lower() in roster_domains for e in emails):
            drops["on-roster"] += 1
            continue
        bio = c.get("bio") or ""
        region = c.get("region")
        name = c.get("name") or ""

        # Geo is soft: only drop on positive wrong-region confirmation, never on absence
        if geo != "any":
            if geo == "UK" and F.is_non_uk(bio, region, name, emails):
                drops["non-geo"] += 1
                continue
            if geo == "US" and F.is_non_us(bio, region):
                drops["non-geo"] += 1
                continue

        if gender == "female" and F.is_male(name, bio, h):
            drops["male"] += 1
            continue
        if gender == "male" and F.is_female(name, bio, h):
            drops["female-required-male-detected"] += 1
            continue

        if F.is_brand(name, h, bio):
            drops["brand"] += 1
            continue

        if "any" not in requested_verticals:
            matched, hits = F.has_vertical(bio, requested_verticals)
            if not matched:
                drops["no-vertical"] += 1
                continue
            c["_vertical_hits"] = hits

        fc = c.get("followerCount") or 0
        if fc and (fc < follower_min // 3 or fc > follower_max * 3):
            drops["out-of-range"] += 1
            continue

        kept.append(c)

    return kept, drops


def rank(kept, requested_verticals, target_geo):
    for c in kept:
        score, reasons = F.score_creator(c, requested_verticals, target_geo)
        c["_score"] = score
        c["_reasons"] = reasons
    kept.sort(key=lambda c: -c["_score"])
    return kept


def build_output_rows(ranked, target_geo="UK", limit=None, start_index=1):
    """Build 20-col sheet rows. NO cap by default: every qualified creator is
    emitted. `limit` is an optional hard cap; `start_index` continues numbering
    on an append/--more run so the master sheet never renumbers existing rows."""
    rows = []
    subset = ranked if limit is None else ranked[:limit]
    for i, c in enumerate(subset, start_index):
        emails = c.get("emails") or []
        et = F.primary_email_type(emails)
        pe = F.primary_email(emails)
        bio_raw = c.get("bio") or ""
        bio = bio_raw.replace("\n", " ")[:400]
        if target_geo == "US":
            geo_tag = F.us_geo_tag(bio_raw, c.get("region")) or "US-unconfirmed"
        elif target_geo == "UK":
            geo_tag = ("UK" if F.is_confirmed_uk(bio_raw, c.get("region"), c.get("name"), emails)
                       else "likely-UK")
        else:
            geo_tag = (c.get("region") or "").strip() or "unknown"
        bio_l = bio_raw.lower()
        if any(k in bio_l for k in F.VERTICAL_KEYWORDS["hair"]):
            vert_label = "hair/beauty"
        elif any(k in bio_l for k in F.VERTICAL_KEYWORDS["fitness"] + F.VERTICAL_KEYWORDS["health"]):
            vert_label = "health/fitness"
        elif any(k in bio_l for k in F.VERTICAL_KEYWORDS["beauty"]):
            vert_label = "beauty"
        else:
            vert_label = "lifestyle"
        rows.append([
            i,
            c["username"],
            F.first_display_name(c.get("name"), c["username"]),
            c.get("name") or "",
            pe,
            et,
            ", ".join(emails),
            c.get("followerCount") or "",
            "",
            "Instagram",
            f"https://instagram.com/{c['username']}",
            bio,
            geo_tag,
            ", ".join(c.get("sources") or []),
            ", ".join(c.get("seed_sources") or []),
            "Y" if et == "agency/mgmt" else "N",
            vert_label,
            c["_score"],
            "Ready for outreach" if et == "personal" else "Mgmt-gated" if et == "agency/mgmt" else "Business email",
            f"{geo_tag} | {' '.join(c['_reasons'])}"[:200],
        ])
    return rows


# ---------------------------------------------------------------------------
# State (persistent cache: enriched pool + already-output handles)
# ---------------------------------------------------------------------------
def _clean(c):
    return {k: v for k, v in c.items() if not k.startswith("_")}


def load_state(path):
    if path and os.path.exists(path):
        try:
            with open(path) as f:
                s = json.load(f)
            return {"candidates": s.get("candidates") or {},
                    "output": s.get("output") or [],
                    "seeds": s.get("seeds") or []}
        except Exception as e:
            log(f"  (state load failed, starting fresh: {type(e).__name__})")
    return {"candidates": {}, "output": [], "seeds": []}


def save_state(path, candidates, output_handles, seeds):
    if not path:
        return
    with open(path, "w") as f:
        json.dump({
            "candidates": {h: _clean(c) for h, c in candidates.items()},
            "output": sorted(set(output_handles)),
            "seeds": sorted(set(seeds)),
        }, f)
    log(f"  State saved -> {path} ({len(candidates)} pooled, {len(set(output_handles))} output-to-date)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="find-creators pipeline")
    p.add_argument("--seeds", default="", help="Comma-separated IG seed handles (URLs/@handles OK). Required for a fresh run.")
    p.add_argument("--target", type=int, default=50,
                   help="Expansion DEPTH knob: raw pool ~= target * multiplier. Does NOT cap output.")
    p.add_argument("--vertical", default="health,fitness,wellness,beauty-health",
                   help="Comma-separated vertical keywords (health|fitness|wellness|beauty|beauty-health|hair|lifestyle|any)")
    p.add_argument("--gender", default="female", choices=["female", "male", "any"])
    p.add_argument("--geo", default="UK", choices=["UK", "US", "AU", "any"])
    p.add_argument("--follower-min", type=int, default=3_000)
    p.add_argument("--follower-max", type=int, default=700_000)
    p.add_argument("--max-rounds", type=int, default=10, help="Max expansion rounds (fresh run)")
    p.add_argument("--raw-multiplier", type=int, default=12, help="Raw pool target = target * this")
    p.add_argument("--batch-size", type=int, default=8, help="Handles expanded per round (fresh run)")
    p.add_argument("--exclude", default="", help="Comma-separated handles to drop from output")
    p.add_argument("--out", required=True, help="Path to write ranked JSON rows (sheet-ready)")
    p.add_argument("--state", help="Persistent state file (enriched pool + already-output handles). "
                                   "Reuse it to cache enrichment and never re-output anyone.")
    p.add_argument("--more", action="store_true",
                   help="Second-pass: reuse --state, re-seed expansion from prior top keepers, append only NEW creators.")
    p.add_argument("--limit", type=int, default=None,
                   help="Optional hard cap on output rows. DEFAULT: none, emit EVERY qualified creator.")
    p.add_argument("--min-enrich-rate", type=float, default=0.10,
                   help="Abort (no empty sheet) if enrichment success rate falls below this (infra-failure guard).")
    p.add_argument("--creator-api-concurrency", type=int, default=48,
                   help="Parallel creator-API requests. 48 was fine on our API; lower it if yours rate-limits.")
    p.add_argument("--dump-all", help="Optional path to dump ALL enriched candidates (debug)")
    args = p.parse_args()

    if not os.environ.get("APIFY_API_TOKEN"):
        log("ERROR: missing env var APIFY_API_TOKEN. Did you "
            "`set -a && source ~/.config/find-creators.env && set +a`?")
        sys.exit(1)
    apify_token = os.environ["APIFY_API_TOKEN"]
    # Optional in-house creator-data API. Unset = Apify does all the enrichment.
    api_base = os.environ.get("CREATOR_API_BASE_URL", "").strip()
    api_token = os.environ.get("CREATOR_API_TOKEN", "").strip()

    run_start_iso = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    verticals = [v.strip() for v in args.vertical.split(",") if v.strip()]

    # --- Load persistent state (cache) ---
    state = load_state(args.state)
    candidates = dict(state["candidates"])
    prior_output = set(state["output"])
    prior_seeds = set(state["seeds"])

    seeds = [s for s in (extract_handle(x) for x in args.seeds.split(",") if x.strip()) if s]
    exclude_handles = {extract_handle(s) for s in args.exclude.split(",") if s.strip()}
    # Seeds + everything ever output are always excluded from output (known already).
    exclude_handles |= set(seeds) | prior_seeds | prior_output

    log(f"=== find-creators run @ {time.strftime('%Y-%m-%d %H:%M:%S')} {'[--more]' if args.more else ''} ===")
    if candidates:
        log(f"Loaded state: {len(candidates)} cached candidates | {len(prior_output)} already output")
    log(f"Verticals: {verticals} | gender: {args.gender} | geo: {args.geo} | "
        f"followers {args.follower_min:,}-{args.follower_max:,} | cap: {args.limit or 'NONE (all qualified)'}")

    # --- Stage 1: Expansion ---
    if args.more:
        if not candidates:
            log("ERROR: --more needs an existing --state with a candidate pool. None found.")
            sys.exit(1)
        prior_kept, _ = apply_filters(candidates, verticals, args.gender, args.geo,
                                      args.follower_min, args.follower_max, extra_exclude=exclude_handles)
        prior_ranked = rank(prior_kept, verticals, args.geo)
        sources = [c["username"] for c in prior_ranked[:96]] or list(candidates)[:96]
        log(f"\n[1/4] --more expansion from {len(sources)} proven keepers")
        new_handles = expand_from(sources, candidates, apify_token)
        log(f"  +{len(new_handles)} new candidates (pool now {len(candidates)})")
    else:
        if not seeds:
            log("ERROR: --seeds required for a fresh run (or use --more with a --state).")
            sys.exit(1)
        target_raw = len(candidates) + args.target * args.raw_multiplier
        log(f"\n[1/4] Expansion (max {args.max_rounds} rounds, batch {args.batch_size}, raw target {target_raw})")
        expand(seeds, apify_token, target_raw, max_rounds=args.max_rounds,
               batch_size=args.batch_size, candidates=candidates)
    log(f"Expansion complete: {len(candidates)} candidates in pool")

    # --- Stage 2: Enrichment (self-healing, cache-aware) ---
    log(f"\n[2/4] Enrichment (creator API primary, Apify profile-scraper fallback)")
    enriched, attempted = enrich_all(candidates, api_base, api_token, apify_token,
                                     concurrency=args.creator_api_concurrency)

    # Sanity gate: catastrophic enrichment failure => stop, don't emit an empty sheet.
    if attempted and (enriched / attempted) < args.min_enrich_rate:
        log(f"\nABORT: enrichment success {enriched}/{attempted} ({enriched/attempted:.0%}) "
            f"below the {args.min_enrich_rate:.0%} floor. Creator API AND Apify likely both failing. "
            f"Refusing to write an empty/near-empty sheet. Fix enrichment and re-run "
            f"(the pool is cached in --state, so this won't re-scrape).")
        save_state(args.state, candidates, prior_output, prior_seeds | set(seeds))
        sys.exit(2)

    if args.dump_all:
        with open(args.dump_all, "w") as f:
            json.dump([_clean(c) for c in candidates.values()], f, indent=2)

    # --- Stage 3: Filter ---
    log(f"\n[3/4] Filter (gender={args.gender}, geo={args.geo})")
    kept, drops = apply_filters(candidates, verticals, args.gender, args.geo,
                                args.follower_min, args.follower_max, extra_exclude=exclude_handles)
    log(f"  Kept: {len(kept)} | Drops: {drops}")

    # --- Stage 4: Rank + build rows (NO CAP: every qualified creator goes in) ---
    log(f"\n[4/4] Rank + build rows")
    ranked = rank(kept, verticals, args.geo)
    start_index = len(prior_output) + 1
    rows = build_output_rows(ranked, target_geo=args.geo, limit=args.limit, start_index=start_index)

    # Stats
    personal = sum(1 for r in rows if r[5] == "personal")
    business = sum(1 for r in rows if r[5] == "business")
    mgmt = sum(1 for r in rows if r[5] == "agency/mgmt")
    micro = sum(1 for r in rows if isinstance(r[7], int) and r[7] < 50_000)
    mid = sum(1 for r in rows if isinstance(r[7], int) and 50_000 <= r[7] < 150_000)
    big = sum(1 for r in rows if isinstance(r[7], int) and r[7] >= 150_000)
    nyc = sum(1 for r in rows if r[12] == "NYC")
    la = sum(1 for r in rows if r[12] == "LA")

    # Persist state: full pool + everyone now output + all seeds seen
    output_handles = prior_output | {r[1] for r in rows}
    save_state(args.state, candidates, output_handles, prior_seeds | set(seeds))

    with open(args.out, "w") as f:
        json.dump({
            "rows": rows,
            "append": args.more or bool(prior_output),
            "start_index": start_index,
            "stats": {
                "pool_size": len(candidates),
                "qualified": len(kept),
                "output_this_run": len(rows),
                "output_to_date": len(output_handles),
                "email_personal": personal, "email_business": business, "email_mgmt": mgmt,
                "micro": micro, "mid": mid, "big": big,
                "nyc": nyc, "la": la,
                "drops": drops,
            },
            "params": vars(args),
        }, f, indent=2)

    spend = apify_spend_since(apify_token, run_start_iso)

    log(f"\n=== RESULTS WRITTEN TO {args.out} ===")
    log(f"Output this run: {len(rows)} creators (rows {start_index}-{start_index + len(rows) - 1}) | "
        f"output to date: {len(output_handles)}")
    log(f"Email split: personal {personal} | business {business} | mgmt {mgmt}")
    log(f"Follower tiers: micro {micro} | mid {mid} | big {big}")
    if args.geo == "US":
        log(f"US cities: NYC {nyc} | LA {la} | other/unconfirmed {len(rows) - nyc - la}")
    if spend is not None:
        log(f"Apify spend this run: ${spend:.2f}")
    log(f"\nTop 10 this run:")
    for r in rows[:10]:
        tag = (r[12] or "?")[:3]
        fc_str = f"{r[7]:,}" if isinstance(r[7], int) else "-"
        log(f"  {tag:3s} {r[17]:3d} @{r[1]:25s} {fc_str:>10s} | {r[3][:25]:25s} ({r[5][:7]})")


if __name__ == "__main__":
    main()
