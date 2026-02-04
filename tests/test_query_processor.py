"""Tests for QueryProcessor service."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from src.schemas.common import QueryType, DataSource
from src.schemas.knowledge import (
    CoverageLookupParams,
    CoverageResult,
    LCDQueryParams,
    LCDResult,
    DenialExplanation,
    PriorAuthResult,
    DataSourceInfo,
)
from src.schemas.query import QueryRequest
from src.services.query_processor import QueryProcessor


class TestQueryClassification:
    """Tests for query classification logic."""

    @pytest.fixture
    def processor(self):
        """Create a QueryProcessor with mocked dependencies."""
        mock_knowledge = MagicMock()
        mock_knowledge.get_data_source_info.return_value = DataSourceInfo(
            type=DataSource.STUBBED,
            last_updated=datetime.now(timezone.utc),
            coverage=[],
        )
        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        return QueryProcessor(knowledge_service=mock_knowledge, db=mock_db)

    def test_classify_coverage_query(self, processor):
        """Test classification of coverage queries."""
        queries = [
            "Is CPT 99213 covered?",
            "What is the coverage for 99214?",
            "Is this procedure covered by Medicare?",
            "Check if 99215 is billable",
        ]
        for query in queries:
            result = processor._classify_query(query)
            assert result == QueryType.COVERAGE_LOOKUP, f"Failed for: {query}"

    def test_classify_lcd_query(self, processor):
        """Test classification of LCD queries."""
        queries = [
            "What does the LCD say about this?",
            "Show me the local coverage determination",
            "What is the Novitas policy?",
            "Check Palmetto MAC region coverage",
        ]
        for query in queries:
            result = processor._classify_query(query)
            assert result == QueryType.LCD_QUERY, f"Failed for: {query}"

    def test_classify_denial_query(self, processor):
        """Test classification of denial queries."""
        queries = [
            "Why was my claim denied?",
            "Explain CARC 16",
            "What does denial code 29 mean?",
            "My claim was rejected",
        ]
        for query in queries:
            result = processor._classify_query(query)
            assert result == QueryType.DENIAL_EXPLANATION, f"Failed for: {query}"

    def test_classify_prior_auth_query(self, processor):
        """Test classification of prior auth queries."""
        queries = [
            "Is prior authorization required?",
            "Do I need pre-auth for this?",
            "Check prior auth requirements",
            "Is PA required for 99213?",
        ]
        for query in queries:
            result = processor._classify_query(query)
            assert result == QueryType.PRIOR_AUTH, f"Failed for: {query}"

    def test_classify_general_query(self, processor):
        """Test classification of general queries."""
        queries = [
            "Hello",
            "What can you help me with?",
            "How does this work?",
        ]
        for query in queries:
            result = processor._classify_query(query)
            assert result == QueryType.GENERAL, f"Failed for: {query}"


class TestCodeExtraction:
    """Tests for code extraction from queries."""

    @pytest.fixture
    def processor(self):
        """Create a QueryProcessor with mocked dependencies."""
        mock_knowledge = MagicMock()
        mock_db = MagicMock()
        return QueryProcessor(knowledge_service=mock_knowledge, db=mock_db)

    def test_extract_cpt_code(self, processor):
        """Test CPT code extraction."""
        assert processor._extract_cpt_code("Check CPT 99213") == "99213"
        assert processor._extract_cpt_code("Is 99214 covered?") == "99214"
        assert processor._extract_cpt_code("No code here") is None

    def test_extract_icd_codes(self, processor):
        """Test ICD code extraction."""
        assert processor._extract_icd_codes("ICD M54.5") == ["M54.5"]
        assert processor._extract_icd_codes("Codes J06.9 and M79.3") == ["J06.9", "M79.3"]
        assert processor._extract_icd_codes("No codes") == []

    def test_extract_carc_code(self, processor):
        """Test CARC code extraction."""
        assert processor._extract_carc_code("CARC 16") == "16"
        assert processor._extract_carc_code("Denial code 29") == "29"
        assert processor._extract_carc_code("Code 96") == "96"

    def test_extract_payer(self, processor):
        """Test payer extraction."""
        assert processor._extract_payer("Medicare coverage") == "Medicare"
        assert processor._extract_payer("Aetna policy") == "Aetna"
        assert processor._extract_payer("UnitedHealthcare plan") == "UnitedHealthcare"
        assert processor._extract_payer("No payer mentioned") is None

    def test_extract_mac_region(self, processor):
        """Test MAC region extraction."""
        assert processor._extract_mac_region("Novitas region") == "Novitas"
        assert processor._extract_mac_region("Palmetto GBA") == "Palmetto"
        assert processor._extract_mac_region("CGS policy") == "CGS"
        assert processor._extract_mac_region("No region") is None
