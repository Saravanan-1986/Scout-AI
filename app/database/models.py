from typing import List, Optional
from pydantic import BaseModel, Field


class EligibilityCriteria(BaseModel):
    years: List[int] = Field(default_factory=list)
    min_cgpa: float = 0.0
    branches: List[str] = Field(default_factory=list)


class StudentProfile(BaseModel):
    user_id: str
    name: str
    degree: str
    department: str
    year: int
    cgpa: float
    skills: List[str] = Field(default_factory=list)
    interests: List[str] = Field(default_factory=list)
    location: str


class Opportunity(BaseModel):
    title: str
    organization: str
    type: str  # "internship" | "competition"
    description: str
    skills: List[str] = Field(default_factory=list)
    eligibility: EligibilityCriteria
    location: str
    stipend_or_prize: Optional[str] = ""
    deadline: Optional[str] = ""
    application_url: Optional[str] = ""
    source_url: Optional[str] = ""


class SavedOpportunity(BaseModel):
    user_id: str
    opportunity_id: str
    status: str  # "saved" | "planning" | "applied"
    saved_date: str
