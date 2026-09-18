from typing import Literal

from pydantic import BaseModel, Field


FindingFlag = Literal["low", "normal", "high", "critical"]
Priority = Literal["routine", "urgent", "immediate"]


class PatientProfile(BaseModel):
    patient_id: str = Field(description="Patient identifier exactly as printed on the report.")
    patient_name: str = Field(description="Full patient name.")
    date_of_birth: str = Field(description="Date of birth in ISO format, or 'unknown'.")
    sex: str = Field(description="Recorded sex, or 'unknown'.")
    encounter_date: str = Field(description="Date the report was produced, or 'unknown'.")


class LabFinding(BaseModel):
    test_name: str = Field(description="Name of the observation or lab test.")
    value: str = Field(description="Measured value as printed, including decimals.")
    unit: str = Field(description="Unit of measure, or an empty string when not applicable.")
    reference_range: str = Field(description="Reference range as printed, or 'not stated'.")
    flag: FindingFlag = Field(description="Whether the value is low, normal, high, or critical.")
    interpretation: str = Field(description="One clinical sentence explaining the value.")


class ReportAnalysis(BaseModel):
    """Structured output of the Report Analysis Agent."""

    patient: PatientProfile
    presenting_concern: str = Field(description="Primary reason for the encounter.")
    history: str = Field(description="Relevant clinical history stated in the report.")
    medications: list[str] = Field(description="Current medications listed in the report.")
    findings: list[LabFinding] = Field(description="Every observation or lab result found.")

    @property
    def abnormal_findings(self) -> list[LabFinding]:
        return [finding for finding in self.findings if finding.flag != "normal"]

    @property
    def has_critical_finding(self) -> bool:
        return any(finding.flag == "critical" for finding in self.findings)


class GuidelineCitation(BaseModel):
    """One retrieved chunk of the medical guideline corpus."""

    title: str
    source: str
    section: str = ""
    excerpt: str = ""
    score: float = 0.0


class ClinicalSummary(BaseModel):
    """Structured output of the Summary Agent."""

    headline: str = Field(description="One-line clinical headline for the reviewing clinician.")
    summary: str = Field(description="Concise narrative summary of the report.")
    key_points: list[str] = Field(description="Short bullet points a clinician should notice.")


class Recommendation(BaseModel):
    action: str = Field(description="Concrete follow-up action for the care team.")
    priority: Priority = Field(description="How soon the action should happen.")
    rationale: str = Field(description="Why this action follows from the findings.")
    supporting_titles: list[str] = Field(
        default_factory=list,
        description="Titles of the supplied guideline excerpts that support this action.",
    )


class RecommendationSet(BaseModel):
    """Structured output of the Recommendation Agent."""

    recommendations: list[Recommendation]
