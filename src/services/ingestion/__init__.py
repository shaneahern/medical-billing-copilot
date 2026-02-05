"""Data ingestion pipeline services for Medical Billing Copilot.

This module provides services for ingesting policy documents from various sources:
- CMS.gov for Medicare LCDs and NCDs (via Downloads, API, or web scraping)
- Commercial payer websites and PDFs
- Manual document uploads

Requirements: 11.1, 11.2, 11.5, 11.6, 11.7, 14.1, 14.2
"""

from src.services.ingestion.cms_api import CMSCoverageAPIClient
from src.services.ingestion.cms_downloads import CMSDownloadsParser
from src.services.ingestion.cms_scraper import CMSDataSource, CMSScraper
from src.services.ingestion.commercial_ingestion import (
    CommercialIngestionService,
    run_commercial_ingestion,
)
from src.services.ingestion.commercial_scraper import CommercialPayerScraper
from src.services.ingestion.medicare_ingestion import (
    MedicareIngestionService,
    run_medicare_ingestion,
)
from src.services.ingestion.orchestrator import IngestionOrchestrator

__all__ = [
    "CMSScraper",
    "CMSDataSource",
    "CMSCoverageAPIClient",
    "CMSDownloadsParser",
    "CommercialPayerScraper",
    "IngestionOrchestrator",
    "MedicareIngestionService",
    "run_medicare_ingestion",
    "CommercialIngestionService",
    "run_commercial_ingestion",
]
