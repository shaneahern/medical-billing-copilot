"""Confidence scoring module for RAG Knowledge Service.

This module provides confidence calculation and low-confidence flagging
for RAG-based responses.

Requirements: 10.4, 10.5, 13.5
"""

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ConfidenceResult:
    """Result of confidence calculation."""

    score: float
    is_low_confidence: bool
    factors: dict[str, float]
    explanation: str


class ConfidenceScorer:
    """Calculate confidence scores for RAG responses.

    Requirements: 10.4, 10.5, 13.5
    """

    def __init__(
        self,
        confidence_threshold: float = 0.6,
        top_k: int = 5,
    ):
        """Initialize the confidence scorer.

        Args:
            confidence_threshold: Threshold below which responses are flagged as low confidence.
            top_k: Expected number of documents to retrieve.
        """
        self.confidence_threshold = confidence_threshold
        self.top_k = top_k

    def calculate_confidence(
        self,
        document_scores: list[float],
        metadata_match_count: int = 0,
        query_specificity: float = 1.0,
    ) -> ConfidenceResult:
        """Calculate confidence score based on multiple factors.

        Requirements: 10.4, 10.5

        Args:
            document_scores: Similarity scores from retrieved documents.
            metadata_match_count: Number of documents matching metadata filters.
            query_specificity: How specific the query is (0-1).

        Returns:
            ConfidenceResult with score and explanation.
        """
        factors = {}

        # Factor 1: Average document similarity score
        if document_scores:
            avg_score = sum(document_scores) / len(document_scores)
            factors["similarity_score"] = avg_score
        else:
            factors["similarity_score"] = 0.0

        # Factor 2: Document coverage (how many relevant docs found)
        coverage = min(len(document_scores) / self.top_k, 1.0) if self.top_k > 0 else 0.0
        factors["document_coverage"] = coverage

        # Factor 3: Top document score (best match quality)
        top_score = max(document_scores) if document_scores else 0.0
        factors["top_document_score"] = top_score

        # Factor 4: Score consistency (are all docs similarly relevant?)
        if len(document_scores) > 1:
            score_variance = sum(
                (s - factors["similarity_score"]) ** 2 for s in document_scores
            ) / len(document_scores)
            consistency = max(0, 1 - score_variance)
        else:
            consistency = 1.0 if document_scores else 0.0
        factors["score_consistency"] = consistency

        # Factor 5: Metadata match bonus
        metadata_bonus = min(metadata_match_count * 0.05, 0.15)
        factors["metadata_match_bonus"] = metadata_bonus

        # Calculate weighted confidence score
        weights = {
            "similarity_score": 0.35,
            "document_coverage": 0.15,
            "top_document_score": 0.25,
            "score_consistency": 0.15,
            "metadata_match_bonus": 0.10,
        }

        confidence = sum(
            factors[factor] * weight for factor, weight in weights.items()
        )

        # Apply query specificity modifier
        confidence *= query_specificity

        # Clamp to [0, 1]
        confidence = max(0.0, min(1.0, confidence))
        confidence = round(confidence, 2)

        # Determine if low confidence
        is_low_confidence = confidence < self.confidence_threshold

        # Generate explanation
        explanation = self._generate_explanation(confidence, factors, is_low_confidence)

        return ConfidenceResult(
            score=confidence,
            is_low_confidence=is_low_confidence,
            factors=factors,
            explanation=explanation,
        )

    def _generate_explanation(
        self,
        confidence: float,
        factors: dict[str, float],
        is_low_confidence: bool,
    ) -> str:
        """Generate human-readable explanation of confidence score."""
        if confidence >= 0.8:
            level = "high"
            reason = "Multiple highly relevant documents found with consistent information."
        elif confidence >= 0.6:
            level = "moderate"
            reason = "Relevant documents found, but some uncertainty in the results."
        elif confidence >= 0.4:
            level = "low"
            reason = "Limited relevant documents found. Results may be incomplete."
        else:
            level = "very low"
            reason = "Few or no relevant documents found. Results should be verified."

        explanation = f"Confidence: {level} ({confidence:.0%}). {reason}"

        if is_low_confidence:
            explanation += " This response is flagged for review."

        return explanation

    def should_flag_response(self, confidence: float) -> bool:
        """Check if a response should be flagged as low confidence.

        Requirements: 10.5, 13.5

        Args:
            confidence: The confidence score.

        Returns:
            True if the response should be flagged.
        """
        return confidence < self.confidence_threshold

    def get_uncertainty_message(self, confidence: float) -> str | None:
        """Get uncertainty message for low-confidence responses.

        Requirements: 10.5, 13.5

        Args:
            confidence: The confidence score.

        Returns:
            Uncertainty message if low confidence, None otherwise.
        """
        if not self.should_flag_response(confidence):
            return None

        if confidence < 0.3:
            return (
                "⚠️ LOW CONFIDENCE: This response is based on limited information. "
                "Please verify with the payer or consult additional sources."
            )
        else:
            return (
                "⚠️ MODERATE UNCERTAINTY: Some aspects of this response may be incomplete. "
                "Consider verifying critical details."
            )


def calculate_relevance_scores(
    documents: list[dict[str, Any]],
    query_terms: list[str],
) -> list[float]:
    """Calculate relevance scores for retrieved documents.

    Requirements: 10.4

    Args:
        documents: List of documents with content and metadata.
        query_terms: Key terms from the query.

    Returns:
        List of relevance scores for each document.
    """
    scores = []

    for doc in documents:
        content = doc.get("content", "").lower()
        metadata = doc.get("metadata", {})

        # Base score from vector similarity (if available)
        base_score = doc.get("score", 0.5)

        # Term match bonus
        term_matches = sum(1 for term in query_terms if term.lower() in content)
        term_bonus = min(term_matches * 0.05, 0.2)

        # Metadata relevance bonus
        metadata_bonus = 0.0
        if metadata.get("source_type") in ["LCD", "NCD", "COMMERCIAL"]:
            metadata_bonus += 0.05
        if metadata.get("effective_date"):
            metadata_bonus += 0.03

        # Calculate final score
        final_score = min(base_score + term_bonus + metadata_bonus, 1.0)
        scores.append(round(final_score, 3))

    return scores
