"""Stubbed Knowledge Service implementation for Medical Billing Copilot.

This module provides a stubbed implementation of the KnowledgeService
interface using static JSON data files for MVP testing.

Now enhanced to search the ingested policy database directly using text matching,
without requiring embeddings or a vector store.

Requirements: 6.2, 6.4, 9.6, 14.4, 14.5
"""

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from src.schemas.common import Citation, ConditionType, DataSource, DenialCategory
from src.schemas.knowledge import (
    AlternativeCode,
    CoverageCondition,
    CoverageLookupParams,
    CoverageResult,
    DataSourceInfo,
    DenialContext,
    DenialExplanation,
    LCDQueryParams,
    LCDResult,
    LCDRevision,
    PlanVariation,
    PriorAuthParams,
    PriorAuthResult,
    RecommendedAction,
)
from src.services.knowledge import KnowledgeService

logger = logging.getLogger(__name__)

# Supported payers list for validation (Requirements 14.5)
SUPPORTED_PAYERS = [
    "medicare",
    "aetna",
    "unitedhealthcare",
    "cigna",
    "humana",
    "anthem",
    "kaiser",
    "bcbs",
    "centene",
    "molina",
    "wellcare",
]


class StubbedKnowledgeService(KnowledgeService):
    """Stubbed implementation of KnowledgeService using JSON files.
    
    This implementation loads policy data from JSON stub files and
    provides all KnowledgeService methods for MVP testing.
    
    Enhanced to search the ingested policy database directly using text matching,
    without requiring embeddings or a vector store.
    
    Requirements: 6.2, 6.4, 9.6, 14.4, 14.5
    """

    def __init__(self, data_path: str = "data/stub"):
        """Initialize the stubbed knowledge service.
        
        Args:
            data_path: Path to the directory containing stub JSON files.
        """
        self.data_path = Path(data_path)
        self._coverage_data: list[dict] = []
        self._lcd_data: list[dict] = []
        self._ncd_data: list[dict] = []
        self._carc_data: list[dict] = []
        self._prior_auth_data: list[dict] = []
        self._mac_regions: list[dict] = []
        self._payers: list[dict] = []
        self._last_updated: datetime = datetime.now(UTC)
        self._policy_db = None
        self._load_data()
        self._load_policy_database()

    def _load_policy_database(self) -> None:
        """Load the policy database for searching ingested documents."""
        try:
            from src.services.policy_database import PolicyDatabase
            self._policy_db = PolicyDatabase(persist_path="data/policy_db_state.json")
            doc_count = len(self._policy_db._documents)
            if doc_count > 0:
                logger.info(f"Loaded policy database with {doc_count} documents")
        except Exception as e:
            logger.warning(f"Could not load policy database: {e}")
            self._policy_db = None

    def _search_policy_database(
        self,
        query_terms: list[str],
        doc_type: Optional[str] = None,
        payer: Optional[str] = None,
        mac_region: Optional[str] = None,
        max_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Search the policy database using text matching.
        
        This performs a simple but effective text search across document
        content and metadata without requiring embeddings or a vector store.
        
        Args:
            query_terms: List of terms to search for (CPT codes, ICD codes, keywords).
            doc_type: Optional filter by document type (LCD, NCD, COMMERCIAL).
            payer: Optional filter by payer name.
            mac_region: Optional filter by MAC region.
            max_results: Maximum number of results to return.
            
        Returns:
            List of matching documents with relevance scores.
        """
        if not self._policy_db:
            return []
        
        results = []
        query_terms_lower = [term.lower() for term in query_terms if term]
        
        for doc_id, metadata in self._policy_db._documents.items():
            # Apply filters
            if doc_type:
                if metadata.document_type.value.upper() != doc_type.upper():
                    continue
            
            if payer:
                doc_payer = (metadata.payer or "").lower()
                if payer.lower() not in doc_payer and doc_payer not in payer.lower():
                    continue
            
            if mac_region:
                doc_mac = (metadata.mac_region or "").upper()
                if mac_region.upper() != doc_mac:
                    continue
            
            # Get document content
            content = self._policy_db._document_content.get(doc_id, "")
            title = metadata.title or ""
            
            # Calculate relevance score based on term matches
            score = 0.0
            matched_terms = []
            
            # Search in title (higher weight)
            title_lower = title.lower()
            for term in query_terms_lower:
                if term in title_lower:
                    score += 3.0
                    matched_terms.append(term)
            
            # Search in content
            content_lower = content.lower()
            for term in query_terms_lower:
                # Count occurrences in content
                count = content_lower.count(term)
                if count > 0:
                    # Logarithmic scaling to prevent very long documents from dominating
                    score += min(count, 10) * 0.5
                    if term not in matched_terms:
                        matched_terms.append(term)
            
            # Boost for exact CPT/ICD code matches (they look like codes)
            for term in query_terms:
                if re.match(r'^\d{5}$', term):  # CPT code pattern
                    if term in content:
                        score += 5.0
                elif re.match(r'^[A-Z]\d{2}\.?\d*$', term, re.IGNORECASE):  # ICD code pattern
                    if term.upper() in content.upper():
                        score += 4.0
            
            if score > 0:
                # Extract relevant snippet from content
                snippet = self._extract_snippet(content, query_terms_lower)
                
                results.append({
                    "document_id": doc_id,
                    "title": title,
                    "document_type": metadata.document_type.value,
                    "payer": metadata.payer,
                    "mac_region": metadata.mac_region,
                    "source_url": metadata.source_url,
                    "effective_date": metadata.effective_date,
                    "score": score,
                    "matched_terms": matched_terms,
                    "snippet": snippet,
                    "content": content,
                })
        
        # Sort by score descending
        results.sort(key=lambda x: x["score"], reverse=True)
        
        return results[:max_results]

    def _extract_snippet(self, content: str, terms: list[str], context_chars: int = 200) -> str:
        """Extract a relevant snippet from content around matched terms.
        
        Args:
            content: The full document content.
            terms: Search terms to find.
            context_chars: Number of characters of context around the match.
            
        Returns:
            A snippet of text containing the matched terms.
        """
        if not content or not terms:
            return content[:context_chars * 2] if content else ""
        
        content_lower = content.lower()
        
        # Find the first matching term
        best_pos = -1
        for term in terms:
            pos = content_lower.find(term)
            if pos != -1 and (best_pos == -1 or pos < best_pos):
                best_pos = pos
        
        if best_pos == -1:
            # No match found, return beginning of content
            return content[:context_chars * 2].strip() + "..."
        
        # Extract snippet around the match
        start = max(0, best_pos - context_chars)
        end = min(len(content), best_pos + context_chars)
        
        snippet = content[start:end].strip()
        
        # Add ellipsis if truncated
        if start > 0:
            snippet = "..." + snippet
        if end < len(content):
            snippet = snippet + "..."
        
        return snippet

    def _build_coverage_from_policy_search(
        self,
        params: CoverageLookupParams,
        search_results: list[dict[str, Any]],
    ) -> Optional[CoverageResult]:
        """Build a CoverageResult from policy database search results.
        
        Args:
            params: The original coverage lookup parameters.
            search_results: Results from policy database search.
            
        Returns:
            CoverageResult if relevant policies found, None otherwise.
        """
        if not search_results:
            return None
        
        # Use the top result as the primary source
        top_result = search_results[0]
        
        # Extract conditions from the content
        conditions: list[CoverageCondition] = []
        restrictions: list[str] = []
        
        content = top_result.get("content", "")
        
        # Look for common coverage indicators in the content
        content_lower = content.lower()
        
        # Check for coverage status indicators
        is_covered = True
        if any(phrase in content_lower for phrase in ["not covered", "non-covered", "excluded", "not medically necessary"]):
            is_covered = False
            restrictions.append("Policy indicates this may not be covered - review full policy details")
        
        # Extract documentation requirements
        doc_patterns = [
            r"documentation (?:must|should|requires?)[^.]*\.",
            r"medical necessity[^.]*\.",
            r"prior authorization[^.]*\.",
        ]
        for pattern in doc_patterns:
            matches = re.findall(pattern, content_lower, re.IGNORECASE)
            for match in matches[:2]:  # Limit to 2 per pattern
                conditions.append(
                    CoverageCondition(
                        type=ConditionType.DOCUMENTATION,
                        description=match.strip().capitalize(),
                    )
                )
        
        # Build citations from search results
        sources = []
        for result in search_results[:3]:  # Top 3 sources
            sources.append(
                Citation(
                    source_type=result["document_type"],
                    document_id=result["document_id"],
                    document_title=result["title"],
                    effective_date=result.get("effective_date"),
                    url=result.get("source_url"),
                )
            )
        
        # Calculate confidence based on search score and number of results
        confidence = min(0.9, 0.5 + (top_result["score"] / 20.0))
        if len(search_results) > 1:
            confidence = min(0.95, confidence + 0.1)
        
        payer = params.payer or "Medicare"
        payer_supported, payer_message = self._check_payer_support(payer)
        
        return CoverageResult(
            cpt_code=params.cpt_code,
            cpt_description=f"Coverage information from {top_result['title']}",
            is_covered=is_covered,
            payer=payer,
            conditions=conditions if conditions else None,
            restrictions=restrictions if restrictions else None,
            alternative_codes=None,
            sources=sources,
            confidence=confidence,
            last_updated=top_result.get("effective_date") or self._last_updated,
            payer_supported=payer_supported,
            payer_support_message=payer_message,
            policy_snippet=top_result.get("snippet"),
        )

    def _load_data(self) -> None:
        """Load all JSON stub files."""
        # Load coverage data
        coverage_file = self.data_path / "coverage.json"
        if coverage_file.exists():
            with open(coverage_file) as f:
                data = json.load(f)
                self._coverage_data = data.get("coverage", [])
                self._payers = data.get("payers", [])
                if "metadata" in data:
                    self._last_updated = datetime.fromisoformat(
                        data["metadata"]["last_updated"].replace("Z", "+00:00")
                    )

        # Load LCD data
        lcd_file = self.data_path / "lcds.json"
        if lcd_file.exists():
            with open(lcd_file) as f:
                data = json.load(f)
                self._lcd_data = data.get("lcds", [])

        # Load NCD data
        ncd_file = self.data_path / "ncds.json"
        if ncd_file.exists():
            with open(ncd_file) as f:
                data = json.load(f)
                self._ncd_data = data.get("ncds", [])

        # Load CARC codes
        carc_file = self.data_path / "carc_codes.json"
        if carc_file.exists():
            with open(carc_file) as f:
                data = json.load(f)
                self._carc_data = data.get("carc_codes", [])

        # Load prior auth data
        prior_auth_file = self.data_path / "prior_auth.json"
        if prior_auth_file.exists():
            with open(prior_auth_file) as f:
                data = json.load(f)
                self._prior_auth_data = data.get("prior_auth", [])

        # Load MAC regions
        mac_file = self.data_path / "mac_regions.json"
        if mac_file.exists():
            with open(mac_file) as f:
                data = json.load(f)
                self._mac_regions = data.get("mac_regions", [])

    async def lookup_coverage(
        self, params: CoverageLookupParams
    ) -> CoverageResult:
        """Look up coverage information for a CPT/ICD combination.
        
        First searches the ingested policy database using text matching,
        then falls back to stub data if no results found.
        
        Requirements: 14.4, 14.5 - Includes last-updated date and payer support status.
        """
        payer = params.payer or "Medicare"
        
        # Check payer support (Requirement 14.5)
        payer_supported, payer_message = self._check_payer_support(payer)
        
        # Build search terms from the query parameters
        search_terms = [params.cpt_code]
        if params.icd_codes:
            search_terms.extend(params.icd_codes)
        
        # Determine document type filter based on payer
        # For Medicare, search LCD and NCD documents
        # For commercial payers, search COMMERCIAL documents
        doc_types_to_search = None
        payer_filter = None
        
        if payer.lower() == "medicare":
            doc_types_to_search = ["LCD", "NCD"]
        else:
            doc_types_to_search = ["COMMERCIAL"]
            payer_filter = payer
        
        # Search the policy database first
        all_results = []
        for doc_type in doc_types_to_search:
            results = self._search_policy_database(
                query_terms=search_terms,
                doc_type=doc_type,
                payer=payer_filter,
                mac_region=params.mac_region,
                max_results=5,
            )
            all_results.extend(results)
        
        # Sort combined results by score
        all_results.sort(key=lambda x: x["score"], reverse=True)
        search_results = all_results[:5]
        
        # If we found relevant policies, build result from them
        if search_results:
            policy_result = self._build_coverage_from_policy_search(params, search_results)
            if policy_result:
                logger.info(f"Found coverage info from policy database for CPT {params.cpt_code}")
                return policy_result
        
        # Fall back to stub data
        matching_coverage = None
        for record in self._coverage_data:
            if (
                record["cpt_code"] == params.cpt_code
                and record["payer"].lower() == payer.lower()
            ):
                matching_coverage = record
                break

        if not matching_coverage:
            # Return not covered result with alternative suggestions
            return CoverageResult(
                cpt_code=params.cpt_code,
                cpt_description="Unknown procedure code",
                is_covered=False,
                payer=payer,
                conditions=[],
                restrictions=["CPT code not found in coverage database"],
                alternative_codes=self._get_alternative_codes(params.cpt_code),
                sources=[
                    Citation(
                        source_type="STUBBED",
                        document_id="STUB-001",
                        document_title="Stubbed Coverage Database",
                        effective_date=self._last_updated,
                    )
                ],
                confidence=0.0,
                last_updated=self._last_updated,
                payer_supported=payer_supported,
                payer_support_message=payer_message,
            )

        # Check ICD code coverage if provided
        is_covered = True
        conditions: list[CoverageCondition] = []
        restrictions: list[str] = []

        if params.icd_codes:
            icd_mappings = matching_coverage.get("icd_mappings", [])
            for icd_code in params.icd_codes:
                icd_match = next(
                    (m for m in icd_mappings if m["icd_code"] == icd_code),
                    None,
                )
                if icd_match:
                    if not icd_match.get("is_covered", True):
                        is_covered = False
                    for condition in icd_match.get("conditions", []):
                        conditions.append(
                            CoverageCondition(
                                type=ConditionType.DOCUMENTATION,
                                description=condition,
                            )
                        )
                else:
                    restrictions.append(
                        f"ICD code {icd_code} not found in coverage mappings"
                    )

        return CoverageResult(
            cpt_code=params.cpt_code,
            cpt_description=matching_coverage.get("description", ""),
            is_covered=is_covered,
            payer=payer,
            conditions=conditions,
            restrictions=restrictions,
            alternative_codes=None if is_covered else self._get_alternative_codes(params.cpt_code),
            sources=[
                Citation(
                    source_type="LCD" if params.mac_region else "NCD",
                    document_id=f"STUB-COV-{params.cpt_code}",
                    document_title=f"Coverage Policy for {params.cpt_code}",
                    effective_date=self._last_updated,
                )
            ],
            confidence=0.95 if is_covered else 0.5,
            last_updated=self._last_updated,
            payer_supported=payer_supported,
            payer_support_message=payer_message,
        )

    def _check_payer_support(self, payer: str) -> tuple[bool, Optional[str]]:
        """Check if a payer is supported in the database.
        
        Requirements: 14.5
        
        Args:
            payer: The payer name to check.
            
        Returns:
            Tuple of (is_supported, message_if_not_supported).
        """
        payer_lower = payer.lower().replace(" ", "")
        
        # Check against supported payers list
        for supported in SUPPORTED_PAYERS:
            if supported in payer_lower or payer_lower in supported:
                return True, None
        
        # Payer not supported
        message = (
            f"The payer '{payer}' is not currently supported in our policy database. "
            f"Please contact the payer directly for coverage information. "
            f"Supported payers include: Medicare, Aetna, UnitedHealthcare, Cigna, Humana, "
            f"Anthem, Kaiser, BCBS, Centene, Molina, and WellCare."
        )
        return False, message

    def _get_alternative_codes(self, cpt_code: str) -> list[AlternativeCode]:
        """Get alternative CPT codes for a non-covered code."""
        # Simple logic to suggest related E/M codes
        em_codes = ["99211", "99212", "99213", "99214", "99215"]
        if cpt_code in em_codes:
            alternatives = []
            for code in em_codes:
                if code != cpt_code:
                    alternatives.append(
                        AlternativeCode(
                            cpt_code=code,
                            description=f"E/M visit level {code[-1]}",
                            reason="Consider different complexity level",
                        )
                    )
            return alternatives[:2]  # Return top 2 alternatives
        return []

    async def query_lcd(self, params: LCDQueryParams) -> LCDResult:
        """Query Local Coverage Determination by MAC region.
        
        Requirements: 14.4 - Includes last-updated date.
        """
        # Find matching LCD
        matching_lcd = None
        for lcd in self._lcd_data:
            if lcd["mac_region"].upper() == params.mac_region.upper():
                if params.lcd_id and lcd["lcd_id"] != params.lcd_id:
                    continue
                if params.cpt_code and params.cpt_code not in lcd.get(
                    "covered_cpt_codes", []
                ):
                    continue
                matching_lcd = lcd
                break

        if not matching_lcd:
            raise LookupError(
                f"No LCD found for MAC region {params.mac_region}"
                + (f" and CPT code {params.cpt_code}" if params.cpt_code else "")
            )

        # Parse revision history
        revision_history = [
            LCDRevision(
                version=rev["version"],
                effective_date=datetime.fromisoformat(
                    rev["effective_date"].replace("Z", "+00:00")
                ),
                summary=rev["summary"],
            )
            for rev in matching_lcd.get("revision_history", [])
        ]

        return LCDResult(
            lcd_id=matching_lcd["lcd_id"],
            title=matching_lcd["title"],
            mac_region=matching_lcd["mac_region"],
            mac_name=matching_lcd["mac_name"],
            effective_date=datetime.fromisoformat(
                matching_lcd["effective_date"].replace("Z", "+00:00")
            ),
            revision_history=revision_history,
            covered_cpt_codes=matching_lcd.get("covered_cpt_codes", []),
            covered_icd_codes=matching_lcd.get("covered_icd_codes", []),
            limitations=matching_lcd.get("limitations", []),
            documentation_requirements=matching_lcd.get(
                "documentation_requirements", []
            ),
            source_url=matching_lcd.get("source_url", ""),
            last_updated=self._last_updated,
        )

    async def explain_denial_code(
        self, code: str, context: Optional[DenialContext] = None
    ) -> DenialExplanation:
        """Explain a CARC denial code with recommended actions."""
        # Find matching CARC code
        matching_carc = next(
            (c for c in self._carc_data if c["code"] == code),
            None,
        )

        if not matching_carc:
            raise LookupError(f"CARC code {code} not found in database")

        # Parse category
        category_map = {
            "ELIGIBILITY": DenialCategory.ELIGIBILITY,
            "AUTHORIZATION": DenialCategory.AUTHORIZATION,
            "CODING": DenialCategory.CODING,
            "DOCUMENTATION": DenialCategory.DOCUMENTATION,
            "OTHER": DenialCategory.OTHER,
        }
        category = category_map.get(
            matching_carc.get("category", "OTHER"),
            DenialCategory.OTHER,
        )

        # Parse recommended actions
        recommended_actions = [
            RecommendedAction(
                priority=action["priority"],
                action=action["action"],
                details=action.get("details"),
            )
            for action in matching_carc.get("recommended_actions", [])
        ]

        return DenialExplanation(
            carc_code=code,
            category=category,
            short_description=matching_carc.get("short_description", ""),
            detailed_explanation=matching_carc.get("detailed_explanation", ""),
            common_causes=matching_carc.get("common_causes", []),
            recommended_actions=recommended_actions,
            related_codes=matching_carc.get("related_codes"),
        )

    async def lookup_prior_auth(
        self, params: PriorAuthParams
    ) -> PriorAuthResult:
        """Look up prior authorization requirements.
        
        Requirements: 14.4, 14.5 - Includes last-updated date and payer support status.
        """
        # Check payer support (Requirement 14.5)
        payer_supported, payer_message = self._check_payer_support(params.payer)
        
        # Find matching prior auth record
        matching_auth = next(
            (
                pa
                for pa in self._prior_auth_data
                if pa["cpt_code"] == params.cpt_code
                and pa["payer"].lower() == params.payer.lower()
            ),
            None,
        )

        if not matching_auth:
            # Return unknown payer result
            return PriorAuthResult(
                cpt_code=params.cpt_code,
                payer=params.payer,
                is_required=False,
                plan_variations=None,
                submission_requirements=None,
                typical_turnaround=None,
                urgent_exceptions=None,
                contact_info=f"Contact {params.payer} directly for prior auth requirements",
                sources=[
                    Citation(
                        source_type="STUBBED",
                        document_id="STUB-PA-UNKNOWN",
                        document_title="Prior Auth Database - Payer Not Found",
                        effective_date=self._last_updated,
                    )
                ],
                last_updated=self._last_updated,
                payer_supported=payer_supported,
                payer_support_message=payer_message,
            )

        # Parse plan variations
        plan_variations = None
        if matching_auth.get("plan_variations"):
            plan_variations = [
                PlanVariation(
                    plan_type=pv["plan_type"],
                    is_required=pv["is_required"],
                    notes=pv.get("notes"),
                )
                for pv in matching_auth["plan_variations"]
            ]

        return PriorAuthResult(
            cpt_code=params.cpt_code,
            payer=params.payer,
            is_required=matching_auth.get("is_required", False),
            plan_variations=plan_variations,
            submission_requirements=matching_auth.get("submission_requirements"),
            typical_turnaround=matching_auth.get("typical_turnaround"),
            urgent_exceptions=matching_auth.get("urgent_exceptions"),
            contact_info=matching_auth.get("contact_info"),
            sources=[
                Citation(
                    source_type="COMMERCIAL" if params.payer != "Medicare" else "NCD",
                    document_id=f"STUB-PA-{params.cpt_code}-{params.payer}",
                    document_title=f"Prior Auth Policy - {params.payer}",
                    effective_date=self._last_updated,
                )
            ],
            last_updated=self._last_updated,
            payer_supported=payer_supported,
            payer_support_message=payer_message,
        )

    def get_data_source_info(self) -> DataSourceInfo:
        """Get information about the knowledge service data source."""
        coverage_areas = []
        
        # Add payer coverage
        for payer in self._payers:
            coverage_areas.append(f"Payer: {payer['name']}")
        
        # Add MAC region coverage
        for mac in self._mac_regions:
            coverage_areas.append(f"MAC Region: {mac['mac_name']}")
        
        # Add policy database info if available
        if self._policy_db:
            doc_count = len(self._policy_db._documents)
            if doc_count > 0:
                coverage_areas.append(f"Policy Database: {doc_count} documents")

        return DataSourceInfo(
            type=DataSource.STUBBED,
            last_updated=self._last_updated,
            coverage=coverage_areas,
        )

    async def search_policies(
        self,
        query: str,
        payer: Optional[str] = None,
        mac_region: Optional[str] = None,
        max_results: int = 10,
    ) -> list[dict[str, Any]]:
        """Search the policy database using free-form text query.
        
        This method provides a general-purpose text search across all
        ingested policy documents without requiring embeddings or a vector store.
        
        Args:
            query: Free-form search query (can include CPT codes, ICD codes, keywords).
            payer: Optional filter by payer name.
            mac_region: Optional filter by MAC region.
            max_results: Maximum number of results to return.
            
        Returns:
            List of matching documents with relevance scores and snippets.
        """
        # Tokenize the query into search terms
        # Split on whitespace and common punctuation, filter out short terms
        query_terms = re.split(r'[\s,;:]+', query)
        query_terms = [term.strip() for term in query_terms if len(term.strip()) >= 2]
        
        if not query_terms:
            return []
        
        # Determine document type filter based on payer
        doc_type = None
        if payer and payer.lower() != "medicare":
            doc_type = "COMMERCIAL"
        
        results = self._search_policy_database(
            query_terms=query_terms,
            doc_type=doc_type,
            payer=payer if payer and payer.lower() != "medicare" else None,
            mac_region=mac_region,
            max_results=max_results,
        )
        
        # Format results for external consumption
        formatted_results = []
        for result in results:
            formatted_results.append({
                "document_id": result["document_id"],
                "title": result["title"],
                "document_type": result["document_type"],
                "payer": result.get("payer"),
                "mac_region": result.get("mac_region"),
                "source_url": result.get("source_url"),
                "relevance_score": result["score"],
                "matched_terms": result["matched_terms"],
                "snippet": result["snippet"],
            })
        
        return formatted_results

    def get_policy_database_stats(self) -> dict[str, Any]:
        """Get statistics about the policy database.
        
        Returns:
            Dictionary with database statistics including document counts,
            coverage areas, and freshness information.
        """
        if not self._policy_db:
            return {
                "available": False,
                "message": "Policy database not loaded",
            }
        
        stats = self._policy_db.get_statistics()
        return {
            "available": True,
            "total_documents": stats.total_documents,
            "medicare_lcd_count": stats.medicare_lcd_count,
            "medicare_ncd_count": stats.medicare_ncd_count,
            "commercial_policy_count": stats.commercial_policy_count,
            "mac_regions_covered": stats.mac_regions_covered,
            "payers_supported": stats.payers_supported,
            "overall_freshness": stats.overall_freshness,
        }
