"""Human-review request and queue contracts for derived investigation leads."""

from pydantic import BaseModel, Field

from app.models.entities import ReviewStatus


class ReviewRequest(BaseModel):
    decision: ReviewStatus
    note: str | None = Field(default=None, max_length=4000)


class ReviewResponse(BaseModel):
    subject_type: str
    subject_id: str
    decision: ReviewStatus
    review_id: str

