"""Knowledge Service abstraction layer for Medical Billing Copilot.

This module defines the abstract interface for knowledge services,
enabling swappable implementations (stubbed data vs RAG-backed).
"""

from abc import ABC, abstractmethod
from typing import Optional

from src.schemas.knowledge import (
    CoverageLookupParams,
    CoverageResult,
    DataSourceInfo,
    DenialContext,
    DenialExplanation,
    LCDQueryParams,
    LCDResult,
    PriorAuthParams,
    PriorAuthResult,
)


class KnowledgeService(ABC):
    """Abstract base class for knowledge service implementations.
    
    This interface defines the contract for all knowledge service
    implementations, whether backed by stubbed JSON data or a full
    RAG pipeline. All implementations must conform to this interface
    to ensure interchangeability.
    
    Requirements: 6.1, 6.3
    """

    @abstractmethod
    async def lookup_coverage(
        self, params: CoverageLookupParams
    ) -> CoverageResult:
        """Look up coverage information for a CPT/ICD combination.
        
        Args:
            params: Coverage lookup parameters including CPT code,
                   optional ICD codes, payer, and MAC region.
        
        Returns:
            CoverageResult with coverage determination, conditions,
            restrictions, and source citations.
        
        Raises:
            ValueError: If CPT code format is invalid.
            LookupError: If CPT code is not found in the database.
        """
        ...

    @abstractmethod
    async def query_lcd(self, params: LCDQueryParams) -> LCDResult:
        """Query Local Coverage Determination by MAC region.
        
        Args:
            params: LCD query parameters including optional LCD ID,
                   CPT code, and required MAC region.
        
        Returns:
            LCDResult with LCD details, revision history, covered codes,
            limitations, and documentation requirements.
        
        Raises:
            ValueError: If MAC region is invalid.
            LookupError: If no matching LCD is found.
        """
        ...

    @abstractmethod
    async def explain_denial_code(
        self, code: str, context: Optional[DenialContext] = None
    ) -> DenialExplanation:
        """Explain a CARC denial code with recommended actions.
        
        Args:
            code: The CARC code to explain.
            context: Optional context including payer, CPT code,
                    and claim type for tailored explanations.
        
        Returns:
            DenialExplanation with category, description, common causes,
            and recommended corrective actions.
        
        Raises:
            ValueError: If CARC code format is invalid.
            LookupError: If CARC code is not recognized.
        """
        ...

    @abstractmethod
    async def lookup_prior_auth(
        self, params: PriorAuthParams
    ) -> PriorAuthResult:
        """Look up prior authorization requirements.
        
        Args:
            params: Prior auth parameters including CPT code,
                   payer, and optional plan type.
        
        Returns:
            PriorAuthResult with auth requirements, submission details,
            turnaround times, and plan variations.
        
        Raises:
            ValueError: If CPT code format is invalid.
            LookupError: If payer is not supported.
        """
        ...

    @abstractmethod
    def get_data_source_info(self) -> DataSourceInfo:
        """Get information about the knowledge service data source.
        
        Returns:
            DataSourceInfo indicating whether data is from stubbed
            or RAG source, last update time, and coverage areas.
        """
        ...
