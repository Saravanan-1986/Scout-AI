from typing import List, Optional
from pydantic import BaseModel, Field


class StudentProfile(BaseModel):
    """Student profile (spec section 6). Legacy web-form fields kept optional."""

    user_id: str
    name: str
    email: Optional[str] = ""
    college: Optional[str] = ""
    degree: str = "B.Tech"
    department: str = "Computer Science"
    year: int = 3
    cgpa: float
    programming_languages: List[str] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    technologies: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    preferred_locations: List[str] = Field(default_factory=list)
    location: Optional[str] = ""  # legacy single-location field from the web form
    opportunity_types: List[str] = Field(default_factory=list)


class Opportunity(BaseModel):
    """Structured opportunity record (spec section 12 data model)."""

    title: str
    organization: str = "Not specified"
    type: str  # internship | hackathon | coding_competition
    description: str = ""
    location: str = "Not specified"
    mode: str = "Not specified"
    duration: str = "Not specified"
    stipend: str = "Not specified"
    prize: str = "Not specified"
    deadline: str = "Not specified"
    eligibility: str = "Not specified"
    required_skills: List[str] = Field(default_factory=list)
    application_url: str = ""
    source_url: str = ""
    source_name: str = ""
    verified: bool = False
    discovered_at: Optional[str] = None


class SavedOpportunity(BaseModel):
    user_id: str
    opportunity_id: str  # source_url used as the stable key
    saved_at: Optional[str] = None
    application_status: str = "Saved"  # Saved | Applied | Interview | Selected | Rejected

