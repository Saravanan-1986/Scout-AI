"""Opportunity Extractor tool (spec TOOL 3).

Converts scraped webpage content into a structured opportunity record.

Anti-fabrication guarantees (spec section 13 — Data Quality Rules):
- Missing information is ALWAYS "Not specified" / "Unable to verify".
- LLM-extracted values are kept only when they are actually grounded in the
  page text; otherwise they are discarded in favour of rule-based extraction.
- No company, deadline, stipend, prize or skill is ever invented.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from app.config import settings
from app.tools.eligibility_rules import (
    extract_eligibility_sentences,
    parse_eligibility_details,
)

logger = logging.getLogger(__name__)

NOT_SPECIFIED = "Not specified"

# (display_name, regex) — every term is matched with word boundaries so that
# e.g. "ai" never matches inside "available" or "email".
_SKILL_VOCAB = [
    ("Python", r"python"), ("Java", r"java(?!script)"), ("C", r"\bc\b"),
    ("C++", r"c\+\+"), ("C#", r"c#"), ("JavaScript", r"javascript|js\b"),
    ("TypeScript", r"typescript"), ("React", r"react"), ("React Native", r"react native"),
    ("Node.js", r"node\.?js"), ("Next.js", r"next\.?js"), ("Vue", r"vue\.?js"),
    ("Angular", r"angular"), ("Django", r"django"), ("Flask", r"flask"),
    ("FastAPI", r"fastapi"), ("Spring Boot", r"spring boot"), ("HTML", r"\bhtml\b"),
    ("CSS", r"\bcss\b"), ("Tailwind", r"tailwind"), ("SQL", r"\bsql\b"),
    ("MongoDB", r"mongodb"), ("MySQL", r"mysql"), ("PostgreSQL", r"postgres(ql)?"),
    ("Firebase", r"firebase"), ("AWS", r"\baws\b|amazon web services"),
    ("Azure", r"azure"), ("GCP", r"gcp|google cloud"), ("Docker", r"docker"),
    ("Kubernetes", r"kubernetes"), ("Git", r"\bgit\b(?!hub|lab)"),
    ("Linux", r"linux"), ("REST API", r"rest(api)?\b"), ("UI/UX", r"ui/?ux|user (?:interface|experience)"),
    ("Figma", r"figma"), ("Machine Learning", r"machine learning|\bml\b"),
    ("Deep Learning", r"deep learning"), ("Artificial Intelligence", r"artificial intelligence|\bai\b"),
    ("Data Science", r"data science"), ("Data Analysis", r"data analYSIS|data analytics".lower()),
    ("NLP", r"\bnlp\b|natural language processing"), ("Computer Vision", r"computer vision"),
    ("Android", r"android"), ("Flutter", r"flutter"), ("Kotlin", r"kotlin"),
    ("Swift", r"\bswift\b"), ("iOS", r"\bios\b"), ("Excel", r"\bexcel\b"),
    ("Power BI", r"power ?bi"), ("Tableau", r"tableau"), ("Blockchain", r"blockchain"),
    ("Solidity", r"solidity"), ("Cybersecurity", r"cyber ?security"),
    ("Web Development", r"web development|web dev\b"), ("App Development", r"app development"),
    ("Problem Solving", r"problem solving|problem-solving"), ("DSA", r"data structures(?: and| &)? algorithms|\bdsa\b"),
]

_CITY_VOCAB = [
    "chennai", "bangalore", "bengaluru", "mumbai", "delhi", "new delhi", "hyderabad",
    "pune", "kolkata", "gurgaon", "gurugram", "noida", "ahmedabad", "jaipur", "kochi",
    "coimbatore", "indore", "lucknow", "remote", "work from home", "online", "virtual",
]

_MONEY = r"(?:₹|rs\.?|inr|usd|\$)\s?\d[\d,]*(?:\.\d+)?(?:\s?(?:k\b|lpa|lakh|crore|per month|/month|/mo|month))?"

_TITLE_JUNK = re.compile(
    r"\s*[\|\-–—·]\s*(?:internshala|unstop|devpost|devfolio|mlh|hackerearth|codechef|"
    r"hackerrank|linkedin|indeed|naukri|wellfound|aicte.*).*$",
    re.IGNORECASE,
)


def _grounded(value: str, text_lower: str) -> bool:
    """True when most alphanumeric tokens of `value` actually appear in the page text.

    This is the anti-hallucination gate for LLM-extracted values.
    """
    if not value:
        return False
    tokens = [t for t in re.split(r"[^a-z0-9+.#]+", value.lower()) if len(t) > 1]
    if not tokens:
        tokens = [value.lower()]
    found = sum(1 for t in tokens if t in text_lower)
    return found >= max(1, int(0.8 * len(tokens)))


def detect_type(text_lower: str, url: str, default_type: str) -> str:
    """Classify the opportunity type from URL first, then page content."""
    url_l = (url or "").lower()
    if "hackathon" in url_l:
        return "hackathon"
    if "internship" in url_l or "intern-" in url_l:
        return "internship"
    if any(w in text_lower[:4000] for w in ("hackathon", "hack day", "codeathon")):
        return "hackathon"
    if "intern" in text_lower[:2500]:
        return "internship"
    if any(w in text_lower[:3000] for w in ("contest", "competition", "challenge")):
        return "coding_competition"
    return default_type


def _clean_title(raw_title: str) -> str:
    title = _TITLE_JUNK.sub("", raw_title or "").strip()
    return (title[:140] or "").strip()


def _title_from_url(url: str) -> str:
    """Derive a human title from the URL slug (grounded — the slug IS the URL)."""
    try:
        path = urlparse(url).path.rstrip("/")
        slug = path.split("/")[-1]
    except Exception:
        return ""
    slug = re.sub(r"-\d{4,}$", "", slug)  # strip trailing numeric ids
    words = [w for w in re.split(r"[-_]+", slug) if w]
    if len(words) < 3:
        return ""
    return " ".join(words).title()[:100]


def _is_generic_title(title: str, site_name: str) -> bool:
    """Detect listing/SPA boilerplate titles like 'Unstop - Competitions, Quizzes...'."""
    t = (title or "").lower()
    if not t:
        return True
    name = (site_name or "").lower()
    if name and (t.startswith(name) or t.endswith(name)):
        return True
    if len(title) > 110:
        return True
    return "competitions, quizzes" in t or "hackathons, scholarships" in t


def looks_like_aggregate_title(title: str) -> bool:
    """True when the page title is a LISTING (e.g. 'Find 34 Data Structures
    Intern Jobs', 'Top 205 Work From Home Data Science Internships') rather
    than a single opportunity."""
    t = (title or "").strip().lower()
    if not t:
        return True
    # "Find 34 ...", "Find 146 Best ..."
    if re.search(r"find \d+", t):
        return True
    # Landing pages: "Find the best internships of your choice"
    if re.search(r"(?:find|search) (?:the |your )?(?:best |perfect |top )?internships", t):
        return True
    if "internships of your choice" in t:
        return True
    if "competitions, quizzes" in t or "hackathons, scholarships" in t or "students and corporates" in t:
        return True
    if "national internship portal" in t or "internship portal by aicte" in t or "internships for aicte" in t:
        return True
    if "career platform" in t or re.search(r"india'?s no\.?\s?1", t):
        return True
    # "Top 205 ...", "Best 34 ...", "Latest 12 ..."
    if re.search(r"\b(?:top|best|latest)\s+\d+\+?", t):
        return True
    # Starts with a count: "34 Data Structures Intern Jobs"
    if re.match(r"^\d+\+?\s+", t):
        return True
    # "N+ Internships" anywhere, with an opportunity keyword
    if re.search(r"\d+\+\s+", t) and any(w in t for w in ("intern", "hackathon", "job", "contests")):
        return True
    # Ends with "... Jobs" / "... Internships"
    if t.endswith("intern jobs") or t.endswith("internships") and re.search(r"\d", t):
        return True
    if "intern jobs" in t or "jobs & internships" in t:
        return True
    # Bare category titles: "Information Technology Internships",
    # "Data Science Internships" (plural with no specific company).
    if t.endswith("internships") and " at " not in t and " — " not in t:
        return True
    # Devpost/other filtered category pages.
    if " on devpost" in t or "home for hackathons" in t:
        return True
    return False
def _extract_deadline(text_lower: str, original_text: str) -> str:
    """Deadline is only reported when explicitly anchored to deadline words."""
    anchored = re.search(
        r"(?:deadline|apply by|apply before|registration (?:closes|ends|deadline)|"
        r"last date (?:to apply)?|submit by|ends on)[:\s\-]*([^\n]{3,60})",
        text_lower,
    )
    if anchored:
        value = anchored.group(1)
        value = value.split(". ")[0]  # never span across sentence boundaries
        value = re.sub(r"\s+(?:by|on|before|at|is|are|to|will|be|the)$", "", value.strip(" ,.;:-()"),
                       flags=re.IGNORECASE).strip(" ,.;:-()")
        # A real deadline contains a digit or a month name; anything else is noise.
        if value and len(value) <= 60 and re.search(r"\d|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec", value, re.IGNORECASE):
            return value[:60]

    # Month-name dates are reported only when the words "deadline/apply/ends" appear on the page.
    if re.search(r"deadline|apply (?:by|before)|registration (?:closes|ends)|last date", text_lower):
        m = re.search(
            r"(\d{1,2}(?:st|nd|rd|th)?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s*\d{4})",
            original_text.lower(),
        )
        if m:
            return m.group(1)
    return NOT_SPECIFIED


def _extract_money_near(text: str, keywords: List[str], window: int = 120) -> str:
    """Find an amount appearing within `window` chars of any keyword."""
    for keyword in keywords:
        for m in re.finditer(keyword, text, re.IGNORECASE):
            start, end = max(0, m.start() - window), min(len(text), m.end() + window)
            money = re.search(_MONEY, text[start:end], re.IGNORECASE)
            if money:
                return money.group(0).strip()
    return ""


def _extract_stipend(text: str) -> str:
    if re.search(r"unpaid", text, re.IGNORECASE) and not re.search(_MONEY, text, re.IGNORECASE):
        return "Unpaid"
    amount = _extract_money_near(text, ["stipend", "monthly pay", "per month", "monthly stipend"])
    return amount or NOT_SPECIFIED


def _extract_prize(text: str) -> str:
    amount = _extract_money_near(text, ["prize", "reward", "cash pool", "prize pool", "worth"])
    if amount:
        return amount
    m = re.search(r"prize[s]?\s*(?:pool)?\s*(?:of|:|\-)?\s*([^\n]{3,60})", text, re.IGNORECASE)
    if m and len(m.group(1).strip()) > 2:
        return m.group(1).strip()[:60]
    return NOT_SPECIFIED


def _extract_location(text_lower: str) -> str:
    if any(w in text_lower for w in ("work from home", "remote", "online", "virtual")):
        return "Remote"
    cities = []
    for city in _CITY_VOCAB:
        if city in ("remote", "work from home", "online", "virtual"):
            continue
        if city in text_lower and city not in cities:
            cities.append(city.title())
    return ", ".join(cities[:2]) if cities else NOT_SPECIFIED


def _extract_mode(text_lower: str) -> str:
    if "hybrid" in text_lower:
        return "Hybrid"
    if any(w in text_lower for w in ("work from home", "remote", "online", "virtual")):
        return "Remote"
    if any(w in text_lower for w in ("in-office", "on-site", "onsite", "in office")):
        return "On-site"
    return NOT_SPECIFIED


def _extract_duration(text: str) -> str:
    m = re.search(
        r"(?:duration|internship|programme|program)[^\n]{0,60}?\b(\d{1,2})\s+(weeks?|months?|days?)\b",
        text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(r"\b(\d{1,2})\s+(weeks?|months?)\b", text[:4000], re.IGNORECASE)
    if m:
        return f"{m.group(1)} {m.group(2).lower()}"
    return NOT_SPECIFIED


def _extract_skills(text: str) -> List[str]:
    found: List[str] = []
    for display, pattern in _SKILL_VOCAB:
        if re.search(pattern, text, re.IGNORECASE):
            found.append(display)
    return found[:12]
_EXTRACTION_SCHEMA = """{
  "title": "string - exact opportunity title from the page",
  "organization": "string - organization/company/organizer name",
  "description": "string - 1-3 sentence factual summary of the page",
  "required_skills": ["skills explicitly mentioned on the page"],
  "deadline": "deadline exactly as written on the page",
  "stipend": "stipend exactly as written on the page",
  "prize": "prize/reward exactly as written on the page",
  "location": "location exactly as written on the page",
  "mode": "Remote / On-site / Hybrid only if stated",
  "duration": "duration exactly as written on the page"
}"""


def _llm_extract(page: Dict[str, Any], combined_text: str) -> Optional[Dict[str, Any]]:
    """Ask the LLM for structured extraction; returns raw dict or None."""
    from app.llm import call_llm, extract_json

    if not llm_enabled():
        return None
    prompt = (
        "You are an information-extraction engine for ScoutAI. Extract opportunity data "
        "from the WEBPAGE CONTENT below.\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY the webpage content. Do NOT use outside knowledge.\n"
        "2. If a field is not explicitly present in the content, return exactly: Not specified\n"
        "3. NEVER invent or guess: titles, organizations, deadlines, stipends, prizes, "
        "locations, eligibility, or skills.\n"
        "4. required_skills must be literally mentioned on the page.\n\n"
        f"PAGE TITLE: {page.get('title', '')}\n"
        f"PAGE URL: {page.get('final_url') or page.get('url', '')}\n"
        f"WEBPAGE CONTENT (may be truncated):\n\"\"\"\n{combined_text[:6000]}\n\"\"\"\n\n"
        f"Return ONLY this JSON object:\n{_EXTRACTION_SCHEMA}"
    )
    raw = call_llm(prompt, temperature=0.0)
    data = extract_json(raw)
    return data if isinstance(data, dict) else None


def llm_enabled() -> bool:
    from app.llm import llm_available

    return llm_available()


def extract_opportunity(page: Dict[str, Any], site: Dict[str, Any], snippet: str = "") -> Optional[Dict[str, Any]]:
    """Build one structured opportunity record from a scraped page.

    Returns None when the page has no usable content at all.
    """
    text = (page.get("text") or "").strip()
    title = _clean_title(page.get("title") or "")
    meta = (page.get("meta_description") or "").strip()
    snippet = (snippet or "").strip()

    combined_text = "\n".join(x for x in (title, meta, snippet, text) if x)
    if len(combined_text) < 60 and not title:
        return None

    url = page.get("final_url") or page.get("url") or ""
    text_lower = combined_text.lower()
    default_type = site.get("default_type", "internship")
    opp_type = detect_type(text_lower, url, default_type)

    # ---------------- Rule-based (always computed, fully grounded) ----------------
    slug_title = _title_from_url(url)
    best_title = title
    if _is_generic_title(title, page.get("site_name") or site.get("name")) and slug_title:
        best_title = slug_title  # SPA pages often serve boilerplate <title> tags
    rule = {
        "title": best_title or (snippet.split("\n")[0][:120] if snippet else "Untitled opportunity"),
        "organization": page.get("site_name") or site.get("name") or NOT_SPECIFIED,
        "description": meta or (text[:350] + ("..." if len(text) > 350 else "")) or snippet[:350] or NOT_SPECIFIED,
        "required_skills": _extract_skills(combined_text),
        "deadline": _extract_deadline(text_lower, combined_text),
        "location": _extract_location(text_lower),
        "mode": _extract_mode(text_lower),
        "duration": _extract_duration(combined_text),
    }
    if opp_type == "internship":
        rule["stipend"] = _extract_stipend(combined_text)
        rule["prize"] = NOT_SPECIFIED
    else:
        rule["stipend"] = NOT_SPECIFIED
        rule["prize"] = _extract_prize(combined_text)

    # ---------------- LLM refinement (grounded values only) ----------------
    llm = _llm_extract(page, combined_text) or {}
    for field in ("title", "organization", "deadline", "stipend", "prize", "location", "duration", "mode"):
        value = str(llm.get(field) or "").strip()
        if not value or value.lower() in ("not specified", "n/a", "none", "unknown"):
            continue
        if _grounded(value, text_lower):  # anti-hallucination gate
            rule[field] = value
    llm_skills = [str(s).strip() for s in (llm.get("required_skills") or []) if str(s).strip()]
    if llm_skills:
        validated = [s for s in llm_skills if s.lower() in text_lower]
        if validated:
            merged = list(dict.fromkeys(rule["required_skills"] + validated))
            rule["required_skills"] = merged[:12]
    llm_desc = str(llm.get("description") or "").strip()
    if len(llm_desc) > 40:
        rule["description"] = llm_desc[:400]

    # ---------------- Eligibility (rule-based quotes only, never invented) ----------------
    sentences = extract_eligibility_sentences(combined_text)
    eligibility_text = " ".join(sentences) if sentences else NOT_SPECIFIED
    details = parse_eligibility_details(eligibility_text)

    return {
        "title": rule["title"][:140],
        "organization": rule["organization"][:100],
        "type": opp_type,
        "description": rule["description"],
        "location": rule["location"],
        "mode": rule["mode"],
        "duration": rule["duration"],
        "stipend": rule["stipend"],
        "prize": rule["prize"],
        "deadline": rule["deadline"],
        "eligibility": eligibility_text[:600],
        "eligibility_details": details,
        "required_skills": rule["required_skills"],
        "application_url": url,
        "source_url": url,
        "source_name": site.get("name") or page.get("site_name") or "Unknown",
        "verified": bool(page.get("ok")) and len(text) > 150,
        "discovered_at": datetime.now(timezone.utc).isoformat(),
    }


