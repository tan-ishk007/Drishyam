"""Source-grounded multimodal evidence understanding.

The original evidence is the source of truth. Everything in this package produces an enrichment
layer beside it and never in place of it.
"""

from app.evidence_intelligence.confidence import ConfidenceOutcome, band_for, classify
from app.evidence_intelligence.detection import ContentFileTypeDetector, DetectedType
from app.evidence_intelligence.extraction import DeterministicExtractor, ExtractionUnit, RawExtraction
from app.evidence_intelligence.references import SourceReference
from app.evidence_intelligence.schema import (
    RAW_EXTRACTION_VERSION,
    ConfidenceBand,
    FieldProvenance,
    NormalizedRecordDraft,
    ObservationBasis,
    RelationCandidate,
    SourceType,
    ValidationStatus,
)

__all__ = [
    "RAW_EXTRACTION_VERSION",
    "ConfidenceBand",
    "ConfidenceOutcome",
    "ContentFileTypeDetector",
    "DetectedType",
    "DeterministicExtractor",
    "ExtractionUnit",
    "FieldProvenance",
    "NormalizedRecordDraft",
    "ObservationBasis",
    "RawExtraction",
    "RelationCandidate",
    "SourceReference",
    "SourceType",
    "ValidationStatus",
    "band_for",
    "classify",
]
