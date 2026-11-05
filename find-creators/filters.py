"""
Shared filter + scoring logic for the find-creators pipeline.
Extracted from live campaign runs and hardened over several more. DO NOT
re-derive these rules: every list and threshold here exists because a real run
leaked the wrong creators without it.
"""
import os
import re

PERSONAL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "hotmail.co.uk",
    "yahoo.com", "yahoo.co.uk", "icloud.com", "me.com", "protonmail.com",
    "sky.com", "live.com", "live.co.uk", "btinternet.com", "aol.com",
    "aol.co.uk", "msn.com", "googlemail.com",
}

AGENCY_DOMAIN_MARKERS = [
    "mgmt", "management", "agency", "talent", "partner",
    "offlimits", "flairmgmt", "reformationmanagement", "thebookingproject",
    "theaqcagency", "grail-talent", "palettemgmt", "theangelsmgmt",
    "scoutedagency", "thedigitalbrandarchitects", "weberpr", "komi.group",
    "s-creative", "thebloggeragent", "be-talent", "aquariuscreative",
    "district.global", "clementinegroup", "jakerosenentertainment",
    "zgadigital", "niche-commercial", "underwatercreative",
    "m-models", "84world", "yoofgroup", "thesocialpr",
]

# Non-UK cities / countries: drop if present AND no UK city override
NON_UK_LOCATIONS = [
    "miami", "los angeles", " la,", "l.a.", "nyc", "new york",
    "paris", "berlin", "munich", "melbourne", "sydney", "gold coast", "brisbane",
    "toronto", "vancouver", "barcelona", "madrid", "dubai", "abu dhabi",
    "amsterdam", "rome", "milan", "tokyo", "bali", "vienna", "zurich",
    "copenhagen", "stockholm", "oslo", "helsinki", "lisbon", "athens",
    "texas", " tx ", " tx.", "| tx", "ph/tx", "atx", "california",
    "florida", "usa,", " usa ",
    "germany", "italy", "france", "spain", "netherlands", "australia",
    "aus,", " aus ", "aus.", "kuwait", "oman", "rio",
    "boston, ma", "boston ma",
    # --- US states/cities: the original list was far thinner than
    # US_OTHER_TOKENS, so a flood of American creators came back tagged
    # "likely-UK" on a geo=UK run. Keep this in step with US_OTHER_TOKENS.
    "usa", "🇺🇸", "united states", "austin", "dallas", "houston", "chicago",
    "seattle", "san francisco", "san diego", "san jose", "bay area",
    "arizona", "phoenix", "scottsdale", "denver", "nashville", "atlanta",
    "utah", "hawaii", "new jersey", " nj ", "philadelphia", "philly",
    "orlando", "tampa", "las vegas", "minneapolis", "detroit", "portland",
    "sacramento", "colorado", "washington dc", "north carolina",
    "south carolina", "ohio", "michigan", "virginia", "maryland",
    "massachusetts", "connecticut", "pennsylvania", "illinois", "missouri",
    "wisconsin", "oregon", "nevada", "oklahoma", "kansas", "kentucky",
    "alabama", "tennessee", "indiana", "iowa", "idaho", "montana",
    "manhattan", "brooklyn", "hoboken", "long island", "harlem", "tribeca",
    "west hollywood", "weho", "santa monica", "venice beach",
    "beverly hills", "malibu", "calabasas", "socal", "orange county",
    " oc |", "oc |", "hollywood", "studio city", " ny ", "ny,", "| ny",
    # --- Canada ---
    "canada", "🇨🇦", "calgary", "edmonton", "ottawa", "montreal", "winnipeg",
    "mississauga", "brampton", "oshawa", "hamilton, on", " gta ", "gta ",
    "alberta", "ontario", "quebec", "british columbia", " ab ", " on,",
    # --- other non-UK ---
    "india", "🇮🇳", "pakistan", "lebanon", ".lb", "iraq", "kurdish",
    "sulaymaniyah", "erbil", "morocco", "egypt", "qatar", "saudi",
    "new zealand", "🇳🇿", "auckland", "singapore", "philippines", "🇵🇭",
    "vietnam", "🇻🇳", "brazil", "mexico", "colombia", "argentina",
    "poland", "romania", "bulgaria", "turkey", "greece", "portugal",
    "switzerland", "belgium", "denmark", "norway", "sweden", "finland",
    "moscow", "bangkok", "pattaya", "phuket", "kyiv", "kiev", "warsaw",
    "prague", "budapest", "krakow", "riga", "tallinn", "sofia", "belgrade",
    "istanbul", "cairo", "johannesburg", "cape town", "nairobi", "lagos",
    "kuala lumpur", "jakarta", "shanghai", "beijing", "osaka", "busan",
    "seoul", "santiago", "lima,", "bogota", "caracas", "montevideo",
    "back to korea", "korea local",
]

# A country-coded email domain is a strong non-UK signal on its own. `.co.uk`
# and `.uk` are handled by is_confirmed_uk, which runs first.
NON_UK_EMAIL_TLDS = (
    ".de", ".ru", ".fr", ".es", ".it", ".nl", ".pl", ".ca", ".au", ".com.au",
    ".nz", ".in", ".br", ".mx", ".jp", ".cn", ".kr", ".se", ".no", ".dk",
    ".fi", ".pt", ".gr", ".tr", ".ua", ".cz", ".ro", ".bg", ".ae", ".sa",
    ".za", ".sg", ".my", ".th", ".ph", ".id", ".lb", ".us",
)

UK_TOKENS = [
    " uk ", "uk,", "uk)", "🇬🇧", "london", " ldn ", " ldn,", "manchester", "liverpool",
    "leeds", "birmingham", "bristol", "glasgow", "edinburgh", "cardiff",
    "belfast", "brighton", "nottingham", "sheffield", "newcastle",
    "oxford", "british", "england", "britain", "united kingdom",
    "south wales", "north wales", "surrey", "chester", "leicester",
    "lincoln", "lincolnshire", "essex", "kent", "yorkshire", "midlands",
    "cotswolds", "hertfordshire", "herts", "scotland", "scottish",
    "wales", "warrington", "southampton", "uk-based",
    # Genuine UK creators were landing in the "no geo signal" bucket on a
    # live run because the county list stopped at the big cities.
    "cheshire", "yorks", "worcester", "solihull", "wiltshire", "dorset",
    "devon", "cornwall", "norfolk", "suffolk", "somerset", "lancashire",
    "merseyside", "tyne", "durham", "cumbria", "staffordshire",
    "shropshire", "gloucestershire", "berkshire", "buckinghamshire",
    "bucks,", "oxfordshire", "northampton", "derbyshire", "derby",
    "cambridge", "norwich", "plymouth", "exeter", "bath,", "york,",
    "hull", "stoke", "coventry", "wolverhampton", "swansea", "newport",
    "aberdeen", "dundee", "inverness", "sussex", "hampshire", "hants",
    "reading", "milton keynes", "bournemouth", "portsmouth", "preston",
    "blackpool", "bolton", "wigan", "wirral", "salford", "stockport",
    "harrogate", "ipswich", "colchester", "chelmsford", "watford",
    "croydon", "camden", "shoreditch", "hackney", "islington", "clapham",
    ".co.uk", "gb)", "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
]

# --- US geo (added for a US hair-care campaign) ---
# Soft signals: tag NYC / LA / US from bio text. Absence of a token is NOT a drop.
NYC_TOKENS = [
    "nyc", "new york", "manhattan", "brooklyn", " ny ", "ny,", "| ny", "ny |",
    "🗽", "soho", "tribeca", "williamsburg", "west village", "east village",
    "hoboken", "long island", "queens", "harlem", "big apple", "new yorker",
    "ny📍", "ny 📍", "📍ny", " ny/", "/ny ",
]

# Tokens in the US lists that double as common British first names or UK place
# names. Reusing the US lists to police a geo=UK run would drop real UK
# creators on these, so they are skipped in UK mode. (On a live run
# "charlotte", "georgia" and "virginia" would each have binned confirmed-UK
# creators.)
# Two-letter US state codes, matched only against hard delimiters (space, pipe,
# slash, comma) so they can't fire inside an ordinary word. Creators very often
# write only the abbreviation: "AZ |", "AZ/LA", "NYer in the DMV".
# `in`/`or`/`me`/`hi`/`oh`/`ok`/`pa`/`de`/`id`/`la`/`ma` are deliberately absent
# either because they're English words or handled by the city lists.
# `co` (Co Founder, & Co), `ms` (Ms.) and `al` (a name) are excluded too: `co`
# binned a real UK creator whose bio opened "Co Founder of @examplebranduk".
US_STATE_ABBR = [
    "az", "ct", "fl", "ga", "il", "ks", "ky", "md", "mi", "mn", "mo", "nc",
    "nd", "nh", "nj", "nm", "nv", "ny", "ri", "sc", "sd", "tn", "tx",
    "ut", "va", "vt", "wa", "wi", "wv", "wy", "ar", "ia", "ne", "mt", "ak",
]
# Boundary = anything that isn't an ASCII letter/digit, so an emoji glued to the
# code still counts ("📍AZ/LA" was slipping through a fixed delimiter class).
US_ABBR_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:" + "|".join(US_STATE_ABBR) + r")(?![a-z0-9])"
)
# Other unambiguous US-only regional slang
US_SLANG_TOKENS = ["dmv", "nyer", "the dmv", "tri-state area", "pnw"]

US_TOKENS_UNSAFE_FOR_UK = {
    "charlotte", "georgia", "virginia", "florida", "phoenix", "austin",
    "washington dc", "boston", "chester", "hamilton", "richmond", "windsor",
    "warwick", "reading", " oc ", "l.a",
}
LA_TOKENS = [
    "los angeles", "l.a.", "l.a ", " la ", "la,", "| la", "la |", "la 📍", "📍la",
    "west hollywood", "weho", "santa monica", "venice beach", "beverly hills",
    "malibu", "calabasas", "silver lake", "socal", "orange county", " oc ",
    "hollywood", "studio city", " la |", "la📍", "📍la", "la 📍", "l.a",
    "la/oc", "la/ny", "oc/la", "ny/la", " la/", "/la ",
]
US_OTHER_TOKENS = [
    "usa", "🇺🇸", "united states", "miami", "texas", "austin", "dallas",
    "houston", "chicago", "boston", "seattle", "san francisco", "san diego",
    "arizona", "phoenix", "scottsdale", "denver", "nashville", "atlanta",
    "florida", "utah", "hawaii", "new jersey", "philadelphia", "philly",
    "charlotte", "orlando", "tampa", "las vegas", "minneapolis", "detroit",
    "portland", "sacramento", "california", "colorado", "washington dc",
    "north carolina", "south carolina", "georgia", "ohio", "michigan",
    "virginia", "maryland", "massachusetts", "connecticut", "pennsylvania",
    "us based", "us-based", "u.s. based", "american girl in",
]
# Confirmed NOT US: only these cause a drop in geo=US mode
NON_US_LOCATIONS = [
    " uk ", "uk,", "uk)", "🇬🇧", "london", " ldn", "manchester", "united kingdom",
    "england", "britain", "british", "scotland", "wales", "ireland", "dublin",
    "🇮🇪", "australia", "sydney", "melbourne", "brisbane", "gold coast", "🇦🇺",
    "perth,", "auckland", "new zealand", "🇳🇿", "canada", "toronto", "vancouver",
    "🇨🇦", "dubai", "abu dhabi", "paris", "berlin", "munich", "amsterdam",
    "barcelona", "madrid", "milan", "rome", "lisbon", "athens", "vienna",
    "zurich", "copenhagen", "stockholm", "oslo", "helsinki", "tokyo", "seoul",
    "singapore", "hong kong", "bali", "manila", "mumbai", "mexico city",
    "sao paulo", "são paulo", "rio de janeiro",
]

VERTICAL_KEYWORDS = {
    "hair": [
        "hair", "haircare", "hair care", "curly", "curls", "blonde", "brunette",
        "hair tips", "healthy hair", "hair journey", "hair growth", "hair routine",
        "extensions", "scalp",
    ],
    "health": [
        "hormone health", "wellness", "holistic", "nutrition", "gut health",
        "women's health", "womens health", "self care", "self-care",
        "mental health", "mindset", "healthy habits", "clean eating",
        "non-toxic", "wellbeing", "well-being", "healing", "functional",
        "hormone", "gut", "healthy meals", "healthy eating",
    ],
    "fitness": [
        "hyrox", "gym", "pilates", "athlete", "strength", "trainer",
        "workout", "fitness", "running", "runner", "marathon", "yoga",
        "glutes", "hybrid athlete", "lifting", "lifts", "gym girl",
        "gym girlie", "calisthenics", "coaching women", "pt ",
        "personal trainer", "build muscle", "fat loss", "training women",
        "sporty", "footballer", "hybrid", "transformation", "runna",
    ],
    "beauty-health": [
        "glow", "skincare", "skin care", "collagen", "beauty from within",
        "skin health", "inside out", "makeup & skin", "skin tips",
    ],
    "beauty": [
        "beauty", "makeup", "skin care", "skincare", "glow", "cosmetic",
        "bridal", "aesthetic", "grwm",
    ],
    "lifestyle": [
        "lifestyle", "routine", "grwm", "day in my life", "vlog",
        "homebody", "home body", "aesthetic", "slow living", "cosy", "cozy",
        "daily life", "morning routine", "evening routine", "mum life",
        "mom life", "mama", "girl things", "girly things", "girlie things",
        "self care", "self-care", "aligned living", "aligned life",
        "mindset", "journaling", "journal", "everyday", "in my 20s",
        "in my 30s", "diary", "day in the life", "day-in-the-life",
        "ootd", "outfit", "wardrobe", "interiors", "home decor",
        "cooking at home", "host at home", "tea time", "girlhood",
        "feminine", "soft life", "soft girl", "soft-girl",
        "hot girl walk", "pilates principles", "wellness routines",
        "balanced living", "intentional living", "lifestyle blogger",
        "lifestyle creator", "lifestyle content",
    ],
    "ugc": [
        "ugc", "ugc creator", "content creator", "ugc content", "ugc & content",
        "ugc and content", "content & ugc", "brand content", "brand photos",
        "iphone content", "content for brands", "events & shoots",
    ],
}

# Email domains that mean "already on our own roster": drop outright, there is
# no point cold-pitching creators we already manage. Set
# FIND_CREATORS_ROSTER_DOMAINS to a comma-separated list of your agency's
# domains, e.g. "youragency.com,mail.youragency.com". Empty = no roster check.
ROSTER_EMAIL_DOMAINS = {
    d.strip().lower()
    for d in os.environ.get("FIND_CREATORS_ROSTER_DOMAINS", "").split(",")
    if d.strip()
}

# Fashion signals that earn a penalty if no health/fitness to offset
PURE_FASHION_MARKERS = [
    "outfit inspo", "fashion creator", "style creator", "ootd",
    "wardrobe", "stylist", "fashion & beauty",
]

MALE_FIRST_NAMES = set("""
aaron adam alan alex alexander andy andrew anthony ben benjamin bradley brandon
brian bruce bryce cameron charles charlie chris christian christopher craig
daniel danny david dean declan dominic ed edward ethan ewan finn francis frank
gabriel gary george grant greg harley harry harrison henry ian jack jackson
jacob james jamie jason jay jeffrey jeremy jeff joe joel john johnny jordan
joseph josh joshua julian justin karl keith kevin kieran kyle lee leo leon
lewis liam louis luke mark martin matt matthew max michael mitch nathan neil
nicholas nick niall oliver olly ollie oscar owen patrick paul peter phil
philip quentin ray richard rick rob robert robin rory ross ryan sam samuel
scott sean sebastian simon stephen steve steven stuart ted theo thomas
tim timothy toby todd tom tony tyler victor vincent will william zack
dave logan travis nate nathaniel wesley wes brett chad dustin garrett
""".split())

FEMALE_FIRST_NAMES = set("""
abigail aimee alexa alexandra alice alicia alisha amanda amber amelia amie amy
ana anna anastasia andrea angela annabel annie aria ariana ashley aubrey ava
bea becky bella bethany beth brooke brooklyn candice cara caroline cat
catherine charlotte chelsea chloe christina christine claire claudia clara
courtney daisy danielle danna darcy dekota denise diana eliza elizabeth ella
ellen ellie emily emma enya erin eva eve evelyn evie faye fiona frankie
frances freya gee gemma georgia georgiana grace hannah harriet hayley heather
helena helene holly hollie imogen isabella isla jade jasmine jenna jennifer
jess jessica jessy jessie jo joanna joanne josie julia julie kate kathryn
kathy kayla keira kelly kim kimberley kirsty kira klaudia laila laura lauren
layla leah leigh leila lexy liana lily linda lisa lizzie lola louise lucy
lydia mackenzie maddy maisy malia maria marie martha mary matilda maya megan
melanie mia michelle millie mindy mollie molly monica monet morgan nadia
natalia natalie natalya neve niamh nicole nikita olivia paige pauli pauline
phoebe polly rachael rachel rebecca rhia rose rosie ruby ruth samantha sara
sarah scarlett simona sophia sophie stacey stella summer susan synead tamara
tanisha tara tasha tegan thea tiffany toria toryia tracey valerie vanessa
vera victoria violet whitney yasmin yuliia zara zoe aaliyah pip devon mia
""".split())

MALE_BIO_MARKERS = [
    " men ", "for men", "helping men", "helping dads", "dad of",
    "husband", " bro ", "he/him", "/him", "men's health",
    "transformation coach for men", "men over", "ambitious men",
    "male content creator", "guy's guide", "dad to",
]

# Unambiguous self-declarations: any single hit is enough to drop in
# gender=female mode (a profile named "MALE MAKEUP ARTIST" once slipped through).
MALE_STRONG_MARKERS = [
    "male makeup artist", "male mua", "male beauty creator", "male model",
    "he/him", "boy dad", "girl dad", "husband &", "husband and",
]

FEMALE_BIO_MARKERS = [
    " mum ", "mum of", "mom of", "mama", "wife", " girl ", "girly", "girlie",
    "grwm", "she/her", "/her", "women's health", "hormone health",
    "girls ", "ladies",
]

BRAND_HANDLE_PATTERNS = [
    r"^hyrox", r"official$", r"^official", r"uk$", r"hq$",
    r"academy$", r"store$", r"shop$", r"worldwide",
]

BRAND_STRONG_BIO = [
    "official channel", "official page", "official account",
    "the world series of", "our mission",
]

# Add the big brand names that crop up as accounts in your niche.
BRAND_NAME_WORDS = [
    "hyrox", "gymshark", "official", "academy",
    " ltd", " inc",
]

# Handles the user has flagged as misses. Add to this after every run: one
# line per handle with a short reason, so the next run never lists them again.
# Kinds of miss that have needed this on live runs:
#   - male creators with a unisex or initial-only name and no bio gender markers
#   - brand, salon, clinic or fashion-retail accounts posing as personas
#   - geo misses the token lists can't catch: a Toronto creator whose only geo
#     signal was a 416 dial code, a "25 | IRE" bio (Republic of Ireland, not
#     UK), a Danish creator routed through a .com agency domain
MANUAL_EXCLUDE = {
    "examplecreator",      # e.g. male creator, no bio gender markers
    "examplebrand.store",  # e.g. retail account, not a persona
}


def first_name_of(name, username):
    if name:
        for t in re.split(r"[\s|.]+", name.strip()):
            t = t.strip()
            if t and t.isalpha() and len(t) >= 2:
                return t.lower()
    pfx = re.split(r"[_.\-0-9]", username)[0]
    return pfx.lower() if pfx and pfx.isalpha() else ""


def is_male(name, bio, username):
    # Search the display name alongside the bio: a profile literally named
    # "MALE MAKEUP ARTIST" passed the female filter on a live run because only
    # the bio was scanned.
    bio_lower = " ".join(f"{bio or ''} {name or ''}".lower().split())
    bio_lower = f" {bio_lower} "
    first = first_name_of(name, username)
    score = 0
    if first in MALE_FIRST_NAMES and first not in FEMALE_FIRST_NAMES:
        score += 3
    elif first in FEMALE_FIRST_NAMES:
        return False
    # Self-declared markers are decisive on their own: the weighted score
    # needs 3 and a lone marker only scores 2, so "MALE MAKEUP ARTIST" with a
    # non-name handle used to squeak through.
    if any(m in bio_lower for m in MALE_STRONG_MARKERS):
        return True
    for m in MALE_BIO_MARKERS:
        if m in bio_lower:
            score += 2
    return score >= 3


def is_female(name, bio, username):
    first = first_name_of(name, username)
    if first in FEMALE_FIRST_NAMES and first not in MALE_FIRST_NAMES:
        return True
    bio_lower = (bio or "").lower()
    if any(m in bio_lower for m in FEMALE_BIO_MARKERS):
        return True
    return False


def is_brand(name, username, bio):
    u = (username or "").lower()
    n = (name or "").lower()
    b = (bio or "").lower()
    for p in BRAND_HANDLE_PATTERNS:
        if re.search(p, u):
            return True
    if any(m in b for m in BRAND_STRONG_BIO):
        return True
    if any(w in n for w in BRAND_NAME_WORDS):
        return True
    return False


UK_BOUNDARY_PATTERN = re.compile(r"(?<![a-z0-9])(?:uk|gb)(?![a-z0-9])")


def _geo_haystack(bio, region, name=None):
    """Lowercased bio+region+name with ALL whitespace collapsed to single
    spaces, padded either end.

    Collapsing matters: IG bios are newline-heavy, and space-delimited tokens
    like " uk " or " aus " silently never matched when the token sat at the end
    of a line. That put confirmed-UK creators in the "no geo" bucket and let
    Australian/US ones through a geo=UK run.
    """
    raw = " ".join(filter(None, [bio, region, name])).lower()
    return " " + " ".join(raw.split()) + " "


def is_confirmed_uk(bio, region, name=None, emails=None):
    """UK confirmation from bio/region/name text OR a .co.uk / .uk email domain.

    The email check matters: a lot of genuine UK creators state no city at all
    but route enquiries through a `.co.uk` agency, which is a strong signal.
    """
    h = _geo_haystack(bio, region, name)
    if any(t in h for t in UK_TOKENS):
        return True
    # Standalone "uk"/"gb" against non-alphanumeric boundaries, so slash- and
    # emoji-delimited forms register ("pt/21/uk", "📍uk", "uk|"). The word-token
    # list above only catches space/comma forms, and won't fire inside a handle
    # like "examplebranduk" (preceded by a letter), which is the behaviour we want.
    if UK_BOUNDARY_PATTERN.search(h):
        return True
    for e in (emails or []):
        d = (e or "").lower().rsplit("@", 1)[-1]
        if d.endswith(".co.uk") or d.endswith(".uk"):
            return True
    return False


def is_non_uk(bio, region, name=None, emails=None):
    # `name` is checked too: enrichment sources often carry the location in the
    # display name only (e.g. "Toronto Makeup Artist" with a geo-free bio).
    h = _geo_haystack(bio, region, name)
    # Expat override: a stated location beats a nationality token. Without this
    # "Scottish girly in Dubai" and "British living in Dubai" both read as UK
    # because `scottish`/`british` win the UK check.
    if re.search(r"\b(?:living|based|now|currently)\s+in\s+([a-z ]{3,20})", h):
        where = re.search(r"\b(?:living|based|now|currently)\s+in\s+([a-z ]{3,20})", h).group(1)
        if not any(t.strip() in where for t in UK_TOKENS if len(t.strip()) > 3):
            if any(t.strip() and t.strip() in where for t in NON_UK_LOCATIONS if len(t.strip()) > 3):
                return True
    if re.search(r"\b(?:girly|girl|lass|boy)\s+in\s+(dubai|abu dhabi|bali|dubai)", h):
        return True
    if is_confirmed_uk(bio, region, name, emails):
        return False
    if any(t in h for t in NON_UK_LOCATIONS):
        return True
    # Reuse the (much richer) US token lists rather than maintaining a parallel
    # copy inside NON_UK_LOCATIONS: they drifted apart and leaked US creators
    # into a geo=UK run. Skip the tokens that collide with
    # British names/places.
    if any(t in h for t in NYC_TOKENS + LA_TOKENS + US_OTHER_TOKENS
           if t not in US_TOKENS_UNSAFE_FOR_UK):
        return True
    if any(t in h for t in US_SLANG_TOKENS):
        return True
    for e in (emails or []):
        d = (e or "").lower().rsplit("@", 1)[-1].strip()
        if d.endswith(NON_UK_EMAIL_TLDS):
            return True
    return bool(US_ABBR_PATTERN.search(h))


def us_geo_tag(bio, region):
    """Soft US geo tag from bio/region text: 'NYC' | 'LA' | 'US' | ''.
    City tags win over generic US tokens; empty string means unconfirmed, not non-US."""
    h = " " + (bio or "").lower() + " " + (region or "").lower() + " "
    if any(t in h for t in NYC_TOKENS):
        return "NYC"
    if any(t in h for t in LA_TOKENS):
        return "LA"
    if any(t in h for t in US_OTHER_TOKENS):
        return "US"
    return ""


def is_non_us(bio, region):
    """True only when the bio positively confirms a non-US base AND no US signal."""
    if us_geo_tag(bio, region):
        return False
    h = " " + (bio or "").lower() + " " + (region or "").lower() + " "
    return any(t in h for t in NON_US_LOCATIONS)


def primary_email_type(emails):
    for e in emails:
        if e.split("@")[-1].lower() in PERSONAL_DOMAINS:
            return "personal"
    txt = " ".join(emails).lower()
    if any(m in txt for m in AGENCY_DOMAIN_MARKERS):
        return "agency/mgmt"
    return "business"


def primary_email(emails):
    for e in emails:
        if e.split("@")[-1].lower() in PERSONAL_DOMAINS:
            return e
    return emails[0] if emails else ""


def first_display_name(name, username):
    if name:
        for t in re.split(r"[\s|.]+", name.strip()):
            t = t.strip()
            if t and t.isalpha() and len(t) >= 2:
                return t.title()
    pfx = re.split(r"[_.\-0-9]", username)[0]
    return pfx.title() if pfx and pfx.isalpha() and len(pfx) >= 3 else ""


def has_vertical(bio, requested_verticals):
    """
    requested_verticals: list of vertical names (health/fitness/beauty/beauty-health/lifestyle/any)
    Returns (matched_bool, matched_keywords).
    """
    if "any" in requested_verticals:
        return True, []
    b = (bio or "").lower()
    hits = []
    for v in requested_verticals:
        for kw in VERTICAL_KEYWORDS.get(v, []):
            if kw in b:
                hits.append(kw)
    return bool(hits), hits


def score_creator(c, requested_verticals, target_geo):
    """
    Apply the scoring weights learned on live campaigns.
    Returns (score, reason_list).
    """
    bio = (c.get("bio") or "").lower()
    name = c.get("name") or ""
    username = c.get("username", "")
    followers = c.get("followerCount") or 0
    emails = c.get("emails") or []
    region = c.get("region")

    score = 0
    reasons = []

    # Lifestyle-mode flag: when lifestyle is the requested vertical,
    # flip weights: lifestyle becomes a strong bonus, fitness becomes a tilt-away
    # (still kept, but doesn't dominate).
    lifestyle_mode = "lifestyle" in requested_verticals and (
        "fitness" not in requested_verticals or len(requested_verticals) == 1
    )

    # Verticals
    health_hits = [k for k in VERTICAL_KEYWORDS["health"] if k in bio]
    fitness_hits = [k for k in VERTICAL_KEYWORDS["fitness"] if k in bio]
    bhealth_hits = [k for k in VERTICAL_KEYWORDS["beauty-health"] if k in bio]
    lifestyle_hits = [k for k in VERTICAL_KEYWORDS["lifestyle"] if k in bio]
    fashion_hits = [k for k in PURE_FASHION_MARKERS if k in bio]

    if lifestyle_mode:
        l_pts = min(len(lifestyle_hits) * 7, 21)
        if l_pts:
            score += l_pts
            reasons.append(f"life+{l_pts}")
        if bhealth_hits:
            score += 5
            reasons.append("bhealth+5")
        if health_hits:
            score += min(len(health_hits) * 3, 9)
            reasons.append("health+soft")
        if fitness_hits and not lifestyle_hits and not health_hits:
            score -= 5
            reasons.append("pure-fit-5")
        if fashion_hits:
            score += 3
            reasons.append("fashion+3")
    else:
        h_pts = min(len(health_hits) * 7, 21)
        f_pts = min(len(fitness_hits) * 6, 18)
        if h_pts:
            score += h_pts
            reasons.append(f"health+{h_pts}")
        if f_pts:
            score += f_pts
            reasons.append(f"fit+{f_pts}")
        if bhealth_hits:
            score += 5
            reasons.append("bhealth+5")
        if fashion_hits and not health_hits and not fitness_hits:
            score -= 3
            reasons.append("fashion-3")

    # Geography bonus
    if target_geo == "UK" and is_confirmed_uk(bio, region, c.get("name"), c.get("emails")):
        score += 15
        reasons.append("UK+15")
    elif target_geo == "US":
        tag = us_geo_tag(bio, region)
        if tag in ("NYC", "LA"):
            score += 15
            reasons.append(f"{tag}+15")
        elif tag == "US":
            score += 8
            reasons.append("US+8")

    # Hair-content bonus (hair-care briefs): only when hair vertical requested
    if "hair" in requested_verticals:
        hair_hits = [k for k in VERTICAL_KEYWORDS["hair"] if k in bio]
        if hair_hits:
            score += min(len(hair_hits) * 5, 10)
            reasons.append("hair+")

    # Follower tier
    if 3_000 <= followers <= 50_000:
        score += 10
        reasons.append("micro+10")
    elif 50_000 <= followers <= 150_000:
        score += 5
    elif 150_000 <= followers <= 300_000:
        score += 2
    elif 300_000 <= followers <= 700_000:
        score -= 3
    elif followers > 700_000:
        score -= 8
    elif followers < 3_000:
        score -= 3

    # Email
    if emails:
        et = primary_email_type(emails)
        if et == "personal":
            score += 8
            reasons.append("pers-email+8")
        elif et == "agency/mgmt":
            score -= 3
            reasons.append("managed-3")
        else:
            score += 3
            reasons.append("biz+3")

    # Female bonus
    fn = first_name_of(name, username)
    if fn in FEMALE_FIRST_NAMES and fn not in MALE_FIRST_NAMES:
        score += 3

    return score, reasons
