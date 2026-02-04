"""Tests for the data ingestion pipeline.

This module tests the CMS scraper, commercial payer scraper, and
ingestion orchestrator functionality.
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.schemas.ingestion import (
    CMSSearchParams,
    CommercialPayerConfig,
    DocumentChunk,
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
    IngestionSource,
    IngestionStatus,
)
from src.services.ingestion.cms_scraper import CMSScraper
from src.services.ingestion.commercial_scraper import CommercialPayerScraper
from src.services.ingestion.orchestrator import IngestionOrchestrator


class TestCMSScraper:
    """Tests for the CMS.gov scraper."""

    def test_init_default_values(self):
        """Test scraper initializes with default values."""
        scraper = CMSScraper()
        assert scraper.timeout == 30.0
        assert scraper.max_retries == 3
        assert scraper.chunk_size == 1000

    def test_init_custom_values(self):
        """Test scraper initializes with custom values."""
        scraper = CMSScraper(timeout=60.0, max_retries=5, chunk_size=500)
        assert scraper.timeout == 60.0
        assert scraper.max_retries == 5
        assert scraper.chunk_size == 500

    def test_mac_regions_defined(self):
        """Test MAC regions are properly defined."""
        assert "Novitas" in CMSScraper.MAC_REGIONS
        assert "Palmetto" in CMSScraper.MAC_REGIONS
        assert "CGS" in CMSScraper.MAC_REGIONS

    def test_build_lcd_search_params(self):
        """Test LCD search parameter building."""
        scraper = CMSScraper()
        params = CMSSearchParams(
            mac_region="Novitas",
            cpt_code="99213",
            keyword="evaluation",
        )
        query = scraper._build_lcd_search_params(params)
        assert query["Contractor"] == "Novitas"
        assert query["CPTCode"] == "99213"
        assert query["KeyWord"] == "evaluation"

    def test_build_ncd_search_params(self):
        """Test NCD search parameter building."""
        scraper = CMSScraper()
        params = CMSSearchParams(
            cpt_code="99214",
            keyword="office visit",
        )
        query = scraper._build_ncd_search_params(params)
        assert query["CPTCode"] == "99214"
        assert query["KeyWord"] == "office visit"

    def test_create_chunks_empty_content(self):
        """Test chunk creation with empty content."""
        scraper = CMSScraper()
        chunks = scraper._create_chunks("doc1", "")
        assert chunks == []

    def test_create_chunks_small_content(self):
        """Test chunk creation with content smaller than chunk size."""
        scraper = CMSScraper(chunk_size=1000)
        content = "This is a small paragraph."
        chunks = scraper._create_chunks("doc1", content)
        assert len(chunks) == 1
        assert chunks[0].content == content
        assert chunks[0].document_id == "doc1"
        assert chunks[0].chunk_index == 0

    def test_create_chunks_large_content(self):
        """Test chunk creation with content larger than chunk size."""
        scraper = CMSScraper(chunk_size=50)
        content = "First paragraph with some text.\n\nSecond paragraph with more text.\n\nThird paragraph."
        chunks = scraper._create_chunks("doc1", content)
        assert len(chunks) >= 2
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
            assert chunk.document_id == "doc1"

    def test_parse_date_various_formats(self):
        """Test date parsing with various formats."""
        scraper = CMSScraper()
        
        # MM/DD/YYYY
        result = scraper._parse_date("01/15/2024")
        assert result == datetime(2024, 1, 15)
        
        # YYYY-MM-DD
        result = scraper._parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)
        
        # Month DD, YYYY
        result = scraper._parse_date("January 15, 2024")
        assert result == datetime(2024, 1, 15)
        
        # Invalid format
        result = scraper._parse_date("invalid date")
        assert result is None


class TestCommercialPayerScraper:
    """Tests for the commercial payer scraper."""

    def test_init_default_configs(self):
        """Test scraper initializes with default payer configs."""
        scraper = CommercialPayerScraper()
        assert "aetna" in scraper.payer_configs
        assert "unitedhealthcare" in scraper.payer_configs
        assert "cigna" in scraper.payer_configs

    def test_init_custom_configs(self):
        """Test scraper accepts custom payer configs."""
        custom = {
            "custom_payer": CommercialPayerConfig(
                payer_id="custom_payer",
                payer_name="Custom Payer",
                base_url="https://custom.com",
            )
        }
        scraper = CommercialPayerScraper(custom_configs=custom)
        assert "custom_payer" in scraper.payer_configs
        assert scraper.payer_configs["custom_payer"].payer_name == "Custom Payer"

    def test_get_supported_payers(self):
        """Test getting list of supported payers."""
        scraper = CommercialPayerScraper()
        payers = scraper.get_supported_payers()
        assert isinstance(payers, list)
        assert len(payers) > 0
        assert "aetna" in payers

    def test_get_payer_config_exists(self):
        """Test getting config for existing payer."""
        scraper = CommercialPayerScraper()
        config = scraper.get_payer_config("aetna")
        assert config is not None
        assert config.payer_name == "Aetna"

    def test_get_payer_config_not_exists(self):
        """Test getting config for non-existent payer."""
        scraper = CommercialPayerScraper()
        config = scraper.get_payer_config("nonexistent")
        assert config is None

    def test_get_payer_config_case_insensitive(self):
        """Test payer config lookup is case insensitive."""
        scraper = CommercialPayerScraper()
        config = scraper.get_payer_config("AETNA")
        assert config is not None
        assert config.payer_name == "Aetna"

    def test_generate_document_id(self):
        """Test document ID generation."""
        scraper = CommercialPayerScraper()
        doc_id = scraper._generate_document_id("aetna", "https://example.com/policy1")
        assert doc_id.startswith("aetna_")
        assert len(doc_id) > 6

    def test_create_chunks(self):
        """Test chunk creation."""
        scraper = CommercialPayerScraper(chunk_size=50)
        content = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        chunks = scraper._create_chunks("doc1", content)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert chunk.document_id == "doc1"


class TestIngestionOrchestrator:
    """Tests for the ingestion orchestrator."""

    def test_init_default_scrapers(self):
        """Test orchestrator initializes with default scrapers."""
        orchestrator = IngestionOrchestrator()
        assert orchestrator.cms_scraper is not None
        assert orchestrator.commercial_scraper is not None

    def test_init_custom_scrapers(self):
        """Test orchestrator accepts custom scrapers."""
        cms = CMSScraper(timeout=60.0)
        commercial = CommercialPayerScraper(timeout=60.0)
        orchestrator = IngestionOrchestrator(
            cms_scraper=cms,
            commercial_scraper=commercial,
        )
        assert orchestrator.cms_scraper.timeout == 60.0
        assert orchestrator.commercial_scraper.timeout == 60.0

    def test_get_job_not_found(self):
        """Test getting non-existent job returns None."""
        orchestrator = IngestionOrchestrator()
        job = orchestrator.get_job("nonexistent")
        assert job is None

    def test_get_all_jobs_empty(self):
        """Test getting jobs when none exist."""
        orchestrator = IngestionOrchestrator()
        jobs = orchestrator.get_all_jobs()
        assert jobs == []

    def test_get_running_jobs_empty(self):
        """Test getting running jobs when none exist."""
        orchestrator = IngestionOrchestrator()
        jobs = orchestrator.get_running_jobs()
        assert jobs == []

    def test_get_logs_empty(self):
        """Test getting logs when none exist."""
        orchestrator = IngestionOrchestrator()
        logs = orchestrator.get_logs()
        assert logs == []

    def test_log_entry_creation(self):
        """Test log entry creation."""
        orchestrator = IngestionOrchestrator()
        orchestrator._log("job1", "INFO", "Test message", "doc1")
        
        logs = orchestrator.get_logs()
        assert len(logs) == 1
        assert logs[0].job_id == "job1"
        assert logs[0].level == "INFO"
        assert logs[0].message == "Test message"
        assert logs[0].document_id == "doc1"

    def test_clear_logs(self):
        """Test clearing logs."""
        orchestrator = IngestionOrchestrator()
        orchestrator._log("job1", "INFO", "Message 1")
        orchestrator._log("job2", "INFO", "Message 2")
        
        count = orchestrator.clear_logs()
        assert count == 2
        assert orchestrator.get_logs() == []

    def test_get_statistics_initial(self):
        """Test getting initial statistics."""
        orchestrator = IngestionOrchestrator()
        stats = orchestrator.get_statistics()
        
        assert stats["total_jobs"] == 0
        assert stats["completed_jobs"] == 0
        assert stats["failed_jobs"] == 0
        assert stats["running_jobs"] == 0
        assert stats["scheduler_running"] is False

    def test_is_scheduler_running_initial(self):
        """Test scheduler is not running initially."""
        orchestrator = IngestionOrchestrator()
        assert orchestrator.is_scheduler_running() is False

    def test_get_logs_filtered_by_job_id(self):
        """Test filtering logs by job ID."""
        orchestrator = IngestionOrchestrator()
        orchestrator._log("job1", "INFO", "Message 1")
        orchestrator._log("job2", "INFO", "Message 2")
        orchestrator._log("job1", "ERROR", "Message 3")
        
        logs = orchestrator.get_logs(job_id="job1")
        assert len(logs) == 2
        assert all(l.job_id == "job1" for l in logs)

    def test_get_logs_filtered_by_level(self):
        """Test filtering logs by level."""
        orchestrator = IngestionOrchestrator()
        orchestrator._log("job1", "INFO", "Message 1")
        orchestrator._log("job1", "ERROR", "Message 2")
        orchestrator._log("job1", "INFO", "Message 3")
        
        logs = orchestrator.get_logs(level="ERROR")
        assert len(logs) == 1
        assert logs[0].level == "ERROR"


class TestIngestionSchemas:
    """Tests for ingestion schemas."""

    def test_document_metadata_creation(self):
        """Test DocumentMetadata creation."""
        metadata = DocumentMetadata(
            document_id="LCD12345",
            document_type=DocumentType.LCD,
            title="Test LCD",
            source_url="https://cms.gov/lcd/12345",
            mac_region="Novitas",
        )
        assert metadata.document_id == "LCD12345"
        assert metadata.document_type == DocumentType.LCD
        assert metadata.mac_region == "Novitas"

    def test_document_chunk_creation(self):
        """Test DocumentChunk creation."""
        chunk = DocumentChunk(
            chunk_id="doc1_chunk_0",
            document_id="doc1",
            content="Test content",
            chunk_index=0,
        )
        assert chunk.chunk_id == "doc1_chunk_0"
        assert chunk.chunk_index == 0

    def test_ingested_document_creation(self):
        """Test IngestedDocument creation."""
        metadata = DocumentMetadata(
            document_id="doc1",
            document_type=DocumentType.NCD,
            title="Test NCD",
            source_url="https://cms.gov/ncd/1",
        )
        doc = IngestedDocument(
            metadata=metadata,
            content="Full content here",
            chunks=[],
        )
        assert doc.metadata.document_id == "doc1"
        assert doc.content == "Full content here"

    def test_cms_search_params_defaults(self):
        """Test CMSSearchParams default values."""
        params = CMSSearchParams()
        assert params.mac_region is None
        assert params.cpt_code is None
        assert params.limit == 100

    def test_commercial_payer_config(self):
        """Test CommercialPayerConfig creation."""
        config = CommercialPayerConfig(
            payer_id="test",
            payer_name="Test Payer",
            base_url="https://test.com",
            requires_auth=True,
            scrape_method="pdf",
        )
        assert config.payer_id == "test"
        assert config.requires_auth is True
        assert config.scrape_method == "pdf"
