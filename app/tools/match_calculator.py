from typing import Any, Dict
from app.database.models import Opportunity, StudentProfile


def calculate_match_score(student: StudentProfile, opportunity: Opportunity) -> Dict[str, Any]:
    """Calculates weighted match score between a student profile and an opportunity."""
    # 1. Skill Match (40%)
    student_skills = {s.lower() for s in student.skills}
    opp_skills = {s.lower() for s in opportunity.skills}
    if not opp_skills:
        skill_ratio = 1.0
    else:
        matching_skills = student_skills.intersection(opp_skills)
        skill_ratio = len(matching_skills) / len(opp_skills)
    skill_score = skill_ratio * 40.0

    # 2. Education / Branch Match (20%)
    req_branches = [b.lower() for b in opportunity.eligibility.branches]
    if not req_branches or student.department.lower() in req_branches:
        edu_score = 20.0
    else:
        edu_score = 0.0

    # 3. Year Eligibility Match (15%)
    req_years = opportunity.eligibility.years
    if not req_years or student.year in req_years:
        year_score = 15.0
    else:
        year_score = 0.0

    # 4. CGPA Eligibility Match (10%)
    if student.cgpa >= opportunity.eligibility.min_cgpa:
        cgpa_score = 10.0
    else:
        cgpa_score = 0.0

    # 5. Interest Match (10%)
    student_interests = [i.lower() for i in student.interests]
    opp_text = f"{opportunity.title} {opportunity.description}".lower()
    if not student_interests:
        interest_ratio = 1.0
    else:
        matched_interests = sum(1 for interest in student_interests if interest in opp_text)
        interest_ratio = matched_interests / len(student_interests)
    interest_score = interest_ratio * 10.0

    # 6. Location Match (5%)
    stud_loc = student.location.lower()
    opp_loc = opportunity.location.lower()
    if "remote" in opp_loc or "any" in opp_loc or opp_loc in stud_loc or stud_loc in opp_loc:
        location_score = 5.0
    else:
        location_score = 0.0

    total_score = skill_score + edu_score + year_score + cgpa_score + interest_score + location_score

    return {
        "skill_score": round(skill_score, 2),
        "education_score": round(edu_score, 2),
        "year_score": round(year_score, 2),
        "cgpa_score": round(cgpa_score, 2),
        "interest_score": round(interest_score, 2),
        "location_score": round(location_score, 2),
        "total_score": round(total_score, 2),
    }
