"""Tests for Knowledge Service abstraction layer."""

import pytest

from src.schemas.common import DataSource
from src.schemas.knowledge import (
    CoverageLookupParams,
    LCDQueryParams,
    PriorAuthParams,
)
from src.services import KnowledgeService, StubbedKnowledgeService


@pytest.fixture
def stubbed_service() -> StubbedKnowledgeService:
    """Create a stubbed knowledge service instance."""
    return StubbedKnowledgeService()


class TestKnowledgeServiceInterface:
    """Test that StubbedKnowledgeService implements KnowledgeService interface."""

    def test_stubbed_service_is_knowledge_service(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Verify StubbedKnowledgeService is a KnowledgeService."""
        assert isinstance(stubbed_service, KnowledgeService)


class TestDataSourceInfo:
    """Tests for get_data_source_info method."""

    def test_returns_stubbed_data_source(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Verify data source is marked as STUBBED."""
        info = stubbed_service.get_data_source_info()
        assert info.type == DataSource.STUBBED

    def test_includes_coverage_areas(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Verify coverage areas are populated."""
        info = stubbed_service.get_data_source_info()
        assert len(info.coverage) > 0

    def test_includes_last_updated(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Verify last_updated timestamp is set."""
        info = stubbed_service.get_data_source_info()
        assert info.last_updated is not None


class TestCoverageLookup:
    """Tests for lookup_coverage method."""

    @pytest.mark.asyncio
    async def test_lookup_known_cpt_code(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test coverage lookup for a known CPT code."""
        params = CoverageLookupParams(cpt_code="99213", payer="Medicare")
        result = await stubbed_service.lookup_coverage(params)
        
        assert result.cpt_code == "99213"
        assert result.is_covered is True
        assert result.payer == "Medicare"
        assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_lookup_defaults_to_medicare(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that payer defaults to Medicare when not specified."""
        params = CoverageLookupParams(cpt_code="99213")
        result = await stubbed_service.lookup_coverage(params)
        
        assert result.payer == "Medicare"

    @pytest.mark.asyncio
    async def test_lookup_unknown_cpt_code(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test coverage lookup for an unknown CPT code."""
        params = CoverageLookupParams(cpt_code="00000", payer="Medicare")
        result = await stubbed_service.lookup_coverage(params)
        
        assert result.is_covered is False
        assert result.confidence == 0.0

    @pytest.mark.asyncio
    async def test_lookup_with_icd_codes(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test coverage lookup with ICD codes."""
        params = CoverageLookupParams(
            cpt_code="99213",
            icd_codes=["J06.9"],
            payer="Medicare",
        )
        result = await stubbed_service.lookup_coverage(params)
        
        assert result.is_covered is True
        assert len(result.conditions) > 0


class TestLCDQuery:
    """Tests for query_lcd method."""

    @pytest.mark.asyncio
    async def test_query_lcd_by_region(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test LCD query by MAC region."""
        params = LCDQueryParams(mac_region="NOVITAS")
        result = await stubbed_service.query_lcd(params)
        
        assert result.mac_region == "NOVITAS"
        assert result.lcd_id is not None
        assert result.title is not None
        assert result.source_url is not None

    @pytest.mark.asyncio
    async def test_query_lcd_includes_revision_history(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that LCD query includes revision history."""
        params = LCDQueryParams(mac_region="NOVITAS")
        result = await stubbed_service.query_lcd(params)
        
        assert len(result.revision_history) > 0

    @pytest.mark.asyncio
    async def test_query_lcd_unknown_region_raises(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that unknown MAC region raises LookupError."""
        params = LCDQueryParams(mac_region="UNKNOWN")
        
        with pytest.raises(LookupError):
            await stubbed_service.query_lcd(params)


class TestDenialCodeExplanation:
    """Tests for explain_denial_code method."""

    @pytest.mark.asyncio
    async def test_explain_known_carc_code(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test explanation for a known CARC code."""
        result = await stubbed_service.explain_denial_code("4")
        
        assert result.carc_code == "4"
        assert result.short_description is not None
        assert result.detailed_explanation is not None
        assert result.category is not None

    @pytest.mark.asyncio
    async def test_explain_includes_recommended_actions(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that explanation includes recommended actions."""
        result = await stubbed_service.explain_denial_code("4")
        
        assert len(result.recommended_actions) > 0

    @pytest.mark.asyncio
    async def test_explain_unknown_code_raises(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that unknown CARC code raises LookupError."""
        with pytest.raises(LookupError):
            await stubbed_service.explain_denial_code("99999")


class TestPriorAuthLookup:
    """Tests for lookup_prior_auth method."""

    @pytest.mark.asyncio
    async def test_lookup_prior_auth_required(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test prior auth lookup for a procedure requiring auth."""
        params = PriorAuthParams(cpt_code="27447", payer="Aetna")
        result = await stubbed_service.lookup_prior_auth(params)
        
        assert result.cpt_code == "27447"
        assert result.payer == "Aetna"
        assert result.is_required is True
        assert result.submission_requirements is not None

    @pytest.mark.asyncio
    async def test_lookup_prior_auth_not_required(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test prior auth lookup for a procedure not requiring auth."""
        params = PriorAuthParams(cpt_code="99213", payer="Medicare")
        result = await stubbed_service.lookup_prior_auth(params)
        
        assert result.is_required is False

    @pytest.mark.asyncio
    async def test_lookup_prior_auth_includes_plan_variations(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test that prior auth includes plan variations when applicable."""
        params = PriorAuthParams(cpt_code="27447", payer="Aetna")
        result = await stubbed_service.lookup_prior_auth(params)
        
        assert result.plan_variations is not None
        assert len(result.plan_variations) > 0

    @pytest.mark.asyncio
    async def test_lookup_unknown_payer(
        self, stubbed_service: StubbedKnowledgeService
    ):
        """Test prior auth lookup for unknown payer returns graceful response."""
        params = PriorAuthParams(cpt_code="99213", payer="UnknownPayer")
        result = await stubbed_service.lookup_prior_auth(params)
        
        # Should not raise, but return a response indicating payer not found
        assert result.contact_info is not None
        assert "UnknownPayer" in result.contact_info
