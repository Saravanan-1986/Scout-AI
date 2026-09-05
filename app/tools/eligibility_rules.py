"""Shared eligibility parsing + evaluation rules.

Used by the Opportunity Extractor (to structure raw page text) and by the
Eligibility Agent (to compare the student profile against an opportunity).

Design rule: when the source page does not state a requirement, the criterion
is reported as ``unknown`` — ScoutAI never assumes eligibility from missing
information.
"""

import re
from typing import Any, Dict, List

# --------------------------------------------------------------------------- #
# Keyword tables
# --------------------------------------------------------------------------- #

_YEAR_PATTERNS = [
    (r"final[- ]year|graduating (?:student|batch)", [4, 5]),
    (r"pre[- ]final|third year|3rd year|third[- ]year", [3]),
    (r"second year|2nd year|second[- ]year|sophomore", [2]),
    (r"first year|1st year|first[- ]year|freshman", [1]),
]

_BRANCH_TABLE = [
    (["cse", "computer science", "cs/it", "csit"], "Computer Science"),
    (["information technology"], "Information Technology"),
    (["ece", "electronics and communication", "electronics & communication"], "Electronics and Communication"),
    (["eee", "electrical and electronics", "electrical engineering"], "Electrical and Electronics"),
    (["mechanical"], "Mechanical"),
    (["civil"], "Civil"),
    (["mca"], "MCA"),
    (["bca"], "BCA"),
    (["mba"], "MBA"),
    (["aiml", "ai & ml", "ai/ml", "artificial intelligence and machine learning"], "AI/ML"),
    (["data science"], "Data Science"),
]

_OPEN_TO_ALL_PATTERNS = [
    r"open to all",
    r"any (?:branch|stream|degree|discipline|course)",
    r"all (?:branches|streams|degrees)",
    r"no (?:specific )?(?:branch|degree) restriction",
    r"anyone (?:can|may) (?:apply|participate|register)",
    r"all (?:ug|pg)? ?students",
    r"undergraduate and postgraduate",
    r"students? from all",
]

_ELIGIBILITY_KEYWORDS = (
    "eligib", "who can apply", "open to", "must be", "should be", "pursuing",
    "enrolled", "students from", "only for", "only open", "restricted to",
    "final year", "pre-final", "cgpa", "c.g.p.a", "gpa", "percentage",
    "aggregate", "batch of", "graduating", "year of study", " discipline",
    " branch", "requirements",
)


def extract_eligibility_sentences(text: str, max_sentences: int = 8) -> List[str]:
    """Pull sentences from page text that talk about eligibility."""
    if not text:
        return []
    chunks = re.split(r"[\n\.]|\s{3,}", text)
    out: List[str] = []
    for chunk in chunks:
        chunk = chunk.strip()
        lowered = chunk.lower()
        if len(chunk) < 12 or len(chunk) > 400:
            continue
        if any(keyword in lowered for keyword in _ELIGIBILITY_KEYWORDS):
            out.append(chunk)
        if len(out) >= max_sentences:
            break
    return out
def parse_eligibility_details(eligibility_text: str) -> Dict[str, Any]:
    """Parse structured criteria out of eligibility text.

    Returns {"years": [..], "min_cgpa": float|None, "min_percentage": float|None,
             "branches": [..], "open_to_all": bool, "has_info": bool}
    """
    details: Dict[str, Any] = {
        "years": [],
        "min_cgpa": None,
        "min_percentage": None,
        "branches": [],
        "open_to_all": False,
        "has_info": False,
    }
    if not eligibility_text or eligibility_text == "Not specified":
        return details

    lowered = eligibility_text.lower()

    # --- Academic years (union all matches: "3rd and final year" → [3,4,5]) ---
    matched_years: List[int] = []
    for pattern, years in _YEAR_PATTERNS:
        if re.search(pattern, lowered):
            matched_years.extend(years)
    m = re.search(r"(\d)(?:st|nd|rd|th)[ -]year", lowered)
    if m:
        matched_years.append(int(m.group(1)))
    # Sentence-level ordinals: "open to 3rd and final year students" → 3
    for sentence in re.split(r"[.;\n]", lowered):
        if "year" in sentence:
            for om in re.finditer(r"\b(\d)(?:st|nd|rd|th)\b", sentence):
                matched_years.append(int(om.group(1)))
    details["years"] = sorted(set(matched_years))

    # --- Open to all? ---
    if any(re.search(p, lowered) for p in _OPEN_TO_ALL_PATTERNS):
        details["open_to_all"] = True
        details["years"] = []

    # --- CGPA ---
    m = re.search(r"(?:cgpa|c\.g\.p\.a|gpa)[^\d%]{0,25}(\d(?:\.\d{1,2})?)", lowered)
    if m:
        try:
            value = float(m.group(1))
            if 4.0 <= value <= 10.0:
                details["min_cgpa"] = value
        except ValueError:
            pass

    # --- Percentage ---
    m = re.search(r"(\d{2})(?:\.\d+)?\s*%", lowered)
    if not m:
        m = re.search(r"(?:aggregate|percentage|marks)[^\d%]{0,25}(\d{2})(?:\.\d+)?", lowered)
    if m:
        try:
            pct = float(m.group(1))
            if 40 <= pct <= 100:
                details["min_percentage"] = pct
        except ValueError:
            pass

    # --- Branches ---
    if not details["open_to_all"]:
        found: List[str] = []
        for keywords, label in _BRANCH_TABLE:
            if any(kw in lowered for kw in keywords):
                found.append(label)
        details["branches"] = found

    details["has_info"] = bool(
        details["years"]
        or details["min_cgpa"] is not None
        or details["min_percentage"] is not None
        or details["branches"]
        or details["open_to_all"]
    )
    return details
def _dept_matches(student_dept: str, branches: List[str]) -> bool:
    dept = (student_dept or "").lower()
    if not dept:
        return False
    for branch in branches:
        branch_l = branch.lower()
        if branch_l in dept or dept in branch_l:
            return True
        for token in branch_l.split():
            if len(token) > 3 and token in dept:
                return True
    return False


def evaluate_eligibility(profile: Dict[str, Any], details: Dict[str, Any], eligibility_text: str = "") -> Dict[str, Any]:
    """Compare the student profile with parsed opportunity criteria.

    Returns:
        {
          "status": "ELIGIBLE" | "POSSIBLY ELIGIBLE" | "NOT ELIGIBLE" | "UNKNOWN",
          "reason": human-readable explanation,
          "criteria": {"year": "ok|conflict|unknown", "cgpa": ..., "branch": ...},
        }
    """
    student_year = profile.get("year")
    student_cgpa = float(profile.get("cgpa") or 0.0)
    student_dept = profile.get("department") or ""

    conflicts: List[str] = []
    positives: List[str] = []
    unknowns: List[str] = []
    criteria = {"year": "unknown", "cgpa": "unknown", "branch": "unknown"}

    no_info = not details.get("has_info")
    if no_info and (not eligibility_text or eligibility_text == "Not specified"):
        return {
            "status": "UNKNOWN",
            "reason": "The source page does not clearly state eligibility requirements, so eligibility is unable to be verified.",
            "criteria": criteria,
        }

    # --- Year of study ---
    years = details.get("years") or []
    if years and student_year:
        if student_year in years:
            criteria["year"] = "ok"
            positives.append(f"it is open to year {student_year} students")
        else:
            criteria["year"] = "conflict"
            allowed = ", ".join(f"year {y}" for y in years)
            conflicts.append(f"it is restricted to {allowed}, while you are in year {student_year}")
    elif details.get("open_to_all"):
        criteria["year"] = "ok"
        positives.append("it is open to students of all years")
    else:
        unknowns.append("required academic year is not stated")

    # --- CGPA ---
    min_cgpa = details.get("min_cgpa")
    if min_cgpa is not None:
        if student_cgpa >= min_cgpa:
            criteria["cgpa"] = "ok"
            positives.append(f"your CGPA {student_cgpa} meets the minimum of {min_cgpa}")
        else:
            criteria["cgpa"] = "conflict"
            conflicts.append(f"it requires a minimum CGPA of {min_cgpa}, while yours is {student_cgpa}")
    elif details.get("min_percentage") is not None:
        pct = details["min_percentage"]
        approx = student_cgpa * 9.5
        if approx >= pct:
            criteria["cgpa"] = "ok"
            positives.append(f"your CGPA {student_cgpa} (~{approx:.0f}%) meets the {pct}% requirement")
        else:
            criteria["cgpa"] = "conflict"
            conflicts.append(f"it requires {pct}% aggregate, while your CGPA {student_cgpa} is roughly {approx:.0f}%")
    else:
        unknowns.append("no CGPA requirement was stated")

    # --- Branch / department ---
    branches = details.get("branches") or []
    if details.get("open_to_all"):
        criteria["branch"] = "ok"
        positives.append("it is open to all branches")
    elif branches:
        if _dept_matches(student_dept, branches):
            criteria["branch"] = "ok"
            positives.append(f"your department ({student_dept}) matches the preferred branches ({', '.join(branches)})")
        else:
            exclusivity = re.search(r"only|restricted|exclusively|must be from", (eligibility_text or "").lower())
            if exclusivity:
                criteria["branch"] = "conflict"
                conflicts.append(f"it is restricted to {', '.join(branches)} students, while you are in {student_dept}")
            else:
                criteria["branch"] = "unknown"
                unknowns.append(f"preferred branches are {', '.join(branches)} but this is not exclusive")
    else:
        unknowns.append("no department restriction was stated")

    if conflicts:
        status = "NOT ELIGIBLE"
        reason = "Not eligible: " + "; ".join(conflicts) + "."
    elif no_info:
        status = "UNKNOWN"
        reason = "Eligibility is unable to be verified from the source page."
    elif positives and not unknowns:
        status = "ELIGIBLE"
        reason = "Eligible: " + "; ".join(positives) + "."
    elif positives:
        status = "ELIGIBLE"
        reason = "Eligible: " + "; ".join(positives) + ". Unverified: " + "; ".join(unknowns) + "."
    else:
        status = "POSSIBLY ELIGIBLE"
        reason = "No conflicts found with your profile, but " + "; ".join(unknowns) + ", so eligibility is not fully verified."

    return {"status": status, "reason": reason, "criteria": criteria}


