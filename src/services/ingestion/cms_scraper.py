"""CMS.gov scraper for Medicare LCDs and NCDs.

This module implements web scraping for Medicare Local Coverage Determinations (LCDs)
and National Coverage Determinations (NCDs) from CMS.gov.

Requirements: 11.1
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.schemas.ingestion import (
    CMSSearchParams,
    DocumentChunk,
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
)

logger = logging.getLogger(__name__)


class CMSScraper:
    """Scraper for CMS.gov LCD and NCD documents.
    
    This class handles:
    - Searching for LCDs/NCDs on CMS.gov
    - Extracting document content and metadata
    - Handling pagination for large result sets
    - Following document links to get full content
    
    Requirements: 11.1
    """

    # CMS.gov base URLs
    BASE_URL = "https://www.cms.gov"
    LCD_SEARCH_URL = "https://localcoverage.cms.gov/mcd_archive/search-results.aspx"
    NCD_SEARCH_URL = "https://www.cms.gov/medicare-coverage-database/search/ncd-search.aspx"
    LCD_ARCHIVE_URL = "https://localcoverage.cms.gov/mcd_archive/search-results.aspx"
    NCD_DETAIL_URL = "https://www.cms.gov/medicare-coverage-database/view/ncd.aspx"

    # MAC region mappings
    MAC_REGIONS = {
        "Novitas": ["1", "12"],
        "Palmetto": ["11"],
        "CGS": ["15"],
        "WPS": ["5", "8"],
        "NGS": ["6", "K"],
        "First Coast": ["9"],
        "Noridian": ["A", "B", "E", "F"],
    }

    @staticmethod
    def build_lcd_url(lcd_id: str) -> str:
        """Build the correct LCD archive URL.
        
        Args:
            lcd_id: The LCD identifier (numeric, e.g., "33777").
            
        Returns:
            The correct URL format for the LCD archive.
        """
        # Format: https://localcoverage.cms.gov/mcd_archive/search-results.aspx?keyword=L33777
        lcd_keyword = f"L{lcd_id}" if not lcd_id.startswith("L") else lcd_id
        return f"https://localcoverage.cms.gov/mcd_archive/search-results.aspx?keyword={lcd_keyword}"

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        chunk_size: int = 1000,
    ):
        """Initialize the CMS scraper.
        
        Args:
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            chunk_size: Target size for document chunks (in characters).
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "MedicalBillingCopilot/1.0 (Policy Research Bot)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def search_lcds(
        self, params: CMSSearchParams
    ) -> list[DocumentMetadata]:
        """Search for LCDs on CMS.gov.
        
        Args:
            params: Search parameters including MAC region, CPT code, keyword.
            
        Returns:
            List of document metadata for matching LCDs.
        """
        logger.info(f"Searching LCDs with params: {params}")
        results: list[DocumentMetadata] = []
        
        try:
            client = await self._get_client()
            
            # Build search query parameters
            query_params = self._build_lcd_search_params(params)
            
            # Fetch search results page
            response = await client.get(self.LCD_SEARCH_URL, params=query_params)
            response.raise_for_status()
            
            # Parse results
            soup = BeautifulSoup(response.text, "html.parser")
            results = self._parse_lcd_search_results(soup, params.limit)
            
            # Handle pagination if needed
            results = await self._handle_pagination(
                client, soup, results, params.limit, self._parse_lcd_search_results
            )
            
            logger.info(f"Found {len(results)} LCDs")
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching LCDs: {e}")
            raise
        except Exception as e:
            logger.error(f"Error searching LCDs: {e}")
            raise
            
        return results

    async def search_ncds(
        self, params: CMSSearchParams
    ) -> list[DocumentMetadata]:
        """Search for NCDs on CMS.gov.
        
        Args:
            params: Search parameters including CPT code, keyword.
            
        Returns:
            List of document metadata for matching NCDs.
        """
        logger.info(f"Searching NCDs with params: {params}")
        results: list[DocumentMetadata] = []
        
        try:
            client = await self._get_client()
            
            # Build search query parameters
            query_params = self._build_ncd_search_params(params)
            
            # Fetch search results page
            response = await client.get(self.NCD_SEARCH_URL, params=query_params)
            response.raise_for_status()
            
            # Parse results
            soup = BeautifulSoup(response.text, "html.parser")
            results = self._parse_ncd_search_results(soup, params.limit)
            
            # Handle pagination if needed
            results = await self._handle_pagination(
                client, soup, results, params.limit, self._parse_ncd_search_results
            )
            
            logger.info(f"Found {len(results)} NCDs")
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error searching NCDs: {e}")
            raise
        except Exception as e:
            logger.error(f"Error searching NCDs: {e}")
            raise
            
        return results

    async def fetch_lcd_content(
        self, lcd_id: str, mac_region: Optional[str] = None
    ) -> IngestedDocument:
        """Fetch full content of an LCD document.
        
        Args:
            lcd_id: The LCD identifier (e.g., "L12345").
            mac_region: Optional MAC region for context.
            
        Returns:
            IngestedDocument with full content and metadata.
        """
        logger.info(f"Fetching LCD content: {lcd_id}")
        
        try:
            client = await self._get_client()
            
            # Fetch LCD detail page
            response = await client.get(
                self.LCD_DETAIL_URL,
                params={"lcdId": lcd_id}
            )
            response.raise_for_status()
            
            # Parse document
            soup = BeautifulSoup(response.text, "html.parser")
            document = self._parse_lcd_detail(soup, lcd_id, mac_region)
            
            logger.info(f"Successfully fetched LCD {lcd_id}")
            return document
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching LCD {lcd_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching LCD {lcd_id}: {e}")
            raise

    async def fetch_ncd_content(self, ncd_id: str) -> IngestedDocument:
        """Fetch full content of an NCD document.
        
        Args:
            ncd_id: The NCD identifier (e.g., "310.1").
            
        Returns:
            IngestedDocument with full content and metadata.
        """
        logger.info(f"Fetching NCD content: {ncd_id}")
        
        try:
            client = await self._get_client()
            
            # Fetch NCD detail page
            response = await client.get(
                self.NCD_DETAIL_URL,
                params={"ncdId": ncd_id}
            )
            response.raise_for_status()
            
            # Parse document
            soup = BeautifulSoup(response.text, "html.parser")
            document = self._parse_ncd_detail(soup, ncd_id)
            
            logger.info(f"Successfully fetched NCD {ncd_id}")
            return document
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching NCD {ncd_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching NCD {ncd_id}: {e}")
            raise

    async def scrape_all_lcds(
        self, mac_regions: Optional[list[str]] = None
    ) -> list[IngestedDocument]:
        """Scrape all LCDs for specified MAC regions.
        
        Args:
            mac_regions: List of MAC regions to scrape. If None, scrapes all.
            
        Returns:
            List of ingested LCD documents.
        """
        regions = mac_regions or list(self.MAC_REGIONS.keys())
        all_documents: list[IngestedDocument] = []
        
        for region in regions:
            logger.info(f"Scraping LCDs for MAC region: {region}")
            
            params = CMSSearchParams(mac_region=region, limit=500)
            lcd_list = await self.search_lcds(params)
            
            for lcd_meta in lcd_list:
                try:
                    document = await self.fetch_lcd_content(
                        lcd_meta.document_id, region
                    )
                    all_documents.append(document)
                except Exception as e:
                    logger.error(f"Failed to fetch LCD {lcd_meta.document_id}: {e}")
                    continue
        
        return all_documents

    async def scrape_all_ncds(self) -> list[IngestedDocument]:
        """Scrape all NCDs from CMS.gov.
        
        Returns:
            List of ingested NCD documents.
        """
        logger.info("Scraping all NCDs")
        all_documents: list[IngestedDocument] = []
        
        params = CMSSearchParams(document_type=DocumentType.NCD, limit=500)
        ncd_list = await self.search_ncds(params)
        
        for ncd_meta in ncd_list:
            try:
                document = await self.fetch_ncd_content(ncd_meta.document_id)
                all_documents.append(document)
            except Exception as e:
                logger.error(f"Failed to fetch NCD {ncd_meta.document_id}: {e}")
                continue
        
        return all_documents

    def _build_lcd_search_params(self, params: CMSSearchParams) -> dict:
        """Build query parameters for LCD search."""
        query = {}
        
        if params.mac_region:
            query["Contractor"] = params.mac_region
        if params.cpt_code:
            query["CPTCode"] = params.cpt_code
        if params.keyword:
            query["KeyWord"] = params.keyword
            
        return query

    def _build_ncd_search_params(self, params: CMSSearchParams) -> dict:
        """Build query parameters for NCD search."""
        query = {}
        
        if params.cpt_code:
            query["CPTCode"] = params.cpt_code
        if params.keyword:
            query["KeyWord"] = params.keyword
            
        return query

    def _parse_lcd_search_results(
        self, soup: BeautifulSoup, limit: int
    ) -> list[DocumentMetadata]:
        """Parse LCD search results from HTML."""
        results: list[DocumentMetadata] = []
        
        # Find result table/list
        result_rows = soup.select(".search-results tr, .lcd-list-item, [data-lcd-id]")
        
        for row in result_rows[:limit]:
            try:
                metadata = self._extract_lcd_metadata_from_row(row)
                if metadata:
                    results.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse LCD row: {e}")
                continue
                
        return results

    def _parse_ncd_search_results(
        self, soup: BeautifulSoup, limit: int
    ) -> list[DocumentMetadata]:
        """Parse NCD search results from HTML."""
        results: list[DocumentMetadata] = []
        
        # Find result table/list
        result_rows = soup.select(".search-results tr, .ncd-list-item, [data-ncd-id]")
        
        for row in result_rows[:limit]:
            try:
                metadata = self._extract_ncd_metadata_from_row(row)
                if metadata:
                    results.append(metadata)
            except Exception as e:
                logger.warning(f"Failed to parse NCD row: {e}")
                continue
                
        return results

    def _extract_lcd_metadata_from_row(
        self, row: BeautifulSoup
    ) -> Optional[DocumentMetadata]:
        """Extract LCD metadata from a search result row."""
        # Try to find LCD ID
        lcd_id = None
        lcd_link = row.select_one("a[href*='lcd']")
        
        if lcd_link:
            href = lcd_link.get("href", "")
            # Extract LCD ID from URL
            match = re.search(r"lcdId=([A-Z0-9]+)", href, re.IGNORECASE)
            if match:
                lcd_id = match.group(1)
        
        if not lcd_id:
            # Try data attribute
            lcd_id = row.get("data-lcd-id")
            
        if not lcd_id:
            return None
            
        # Extract title
        title_elem = row.select_one(".lcd-title, .title, td:first-child")
        title = title_elem.get_text(strip=True) if title_elem else f"LCD {lcd_id}"
        
        # Extract MAC region
        mac_elem = row.select_one(".mac-region, .contractor")
        mac_region = mac_elem.get_text(strip=True) if mac_elem else None
        
        # Extract effective date
        date_elem = row.select_one(".effective-date, .date")
        effective_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            effective_date = self._parse_date(date_text)
        
        return DocumentMetadata(
            document_id=lcd_id,
            document_type=DocumentType.LCD,
            title=title,
            source_url=self.build_lcd_url(lcd_id),
            mac_region=mac_region,
            effective_date=effective_date,
        )

    def _extract_ncd_metadata_from_row(
        self, row: BeautifulSoup
    ) -> Optional[DocumentMetadata]:
        """Extract NCD metadata from a search result row."""
        # Try to find NCD ID
        ncd_id = None
        ncd_link = row.select_one("a[href*='ncd']")
        
        if ncd_link:
            href = ncd_link.get("href", "")
            # Extract NCD ID from URL
            match = re.search(r"ncdId=([0-9.]+)", href, re.IGNORECASE)
            if match:
                ncd_id = match.group(1)
        
        if not ncd_id:
            ncd_id = row.get("data-ncd-id")
            
        if not ncd_id:
            return None
            
        # Extract title
        title_elem = row.select_one(".ncd-title, .title, td:first-child")
        title = title_elem.get_text(strip=True) if title_elem else f"NCD {ncd_id}"
        
        # Extract effective date
        date_elem = row.select_one(".effective-date, .date")
        effective_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            effective_date = self._parse_date(date_text)
        
        return DocumentMetadata(
            document_id=ncd_id,
            document_type=DocumentType.NCD,
            title=title,
            source_url=f"{self.NCD_DETAIL_URL}?ncdId={ncd_id}",
            effective_date=effective_date,
        )

    def _parse_lcd_detail(
        self, soup: BeautifulSoup, lcd_id: str, mac_region: Optional[str]
    ) -> IngestedDocument:
        """Parse LCD detail page into an IngestedDocument."""
        # Extract title
        title_elem = soup.select_one("h1, .lcd-title, #lcd-title")
        title = title_elem.get_text(strip=True) if title_elem else f"LCD {lcd_id}"
        
        # Extract MAC name
        mac_elem = soup.select_one(".contractor-name, .mac-name")
        mac_name = mac_elem.get_text(strip=True) if mac_elem else mac_region or "Unknown"
        
        # Extract effective date
        date_elem = soup.select_one(".effective-date, [data-effective-date]")
        effective_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            effective_date = self._parse_date(date_text)
        
        # Extract main content
        content_sections = []
        
        # Coverage indications
        coverage_elem = soup.select_one("#coverage-indications, .coverage-section")
        if coverage_elem:
            content_sections.append(f"Coverage Indications:\n{coverage_elem.get_text(strip=True)}")
        
        # Limitations
        limitations_elem = soup.select_one("#limitations, .limitations-section")
        if limitations_elem:
            content_sections.append(f"Limitations:\n{limitations_elem.get_text(strip=True)}")
        
        # Documentation requirements
        doc_req_elem = soup.select_one("#documentation, .documentation-section")
        if doc_req_elem:
            content_sections.append(f"Documentation Requirements:\n{doc_req_elem.get_text(strip=True)}")
        
        # CPT codes
        cpt_elem = soup.select_one("#cpt-codes, .cpt-section")
        if cpt_elem:
            content_sections.append(f"CPT Codes:\n{cpt_elem.get_text(strip=True)}")
        
        # ICD codes
        icd_elem = soup.select_one("#icd-codes, .icd-section")
        if icd_elem:
            content_sections.append(f"ICD Codes:\n{icd_elem.get_text(strip=True)}")
        
        # If no specific sections found, get main content area
        if not content_sections:
            main_content = soup.select_one("main, .main-content, #content, article")
            if main_content:
                content_sections.append(main_content.get_text(strip=True))
        
        full_content = "\n\n".join(content_sections)
        
        # Create metadata
        metadata = DocumentMetadata(
            document_id=lcd_id,
            document_type=DocumentType.LCD,
            title=title,
            source_url=self.build_lcd_url(lcd_id),
            mac_region=mac_region or mac_name,
            effective_date=effective_date,
            last_updated=datetime.utcnow(),
        )
        
        # Create chunks
        chunks = self._create_chunks(lcd_id, full_content)
        
        return IngestedDocument(
            metadata=metadata,
            content=full_content,
            chunks=chunks,
        )

    def _parse_ncd_detail(
        self, soup: BeautifulSoup, ncd_id: str
    ) -> IngestedDocument:
        """Parse NCD detail page into an IngestedDocument."""
        # Extract title
        title_elem = soup.select_one("h1, .ncd-title, #ncd-title")
        title = title_elem.get_text(strip=True) if title_elem else f"NCD {ncd_id}"
        
        # Extract effective date
        date_elem = soup.select_one(".effective-date, [data-effective-date]")
        effective_date = None
        if date_elem:
            date_text = date_elem.get_text(strip=True)
            effective_date = self._parse_date(date_text)
        
        # Extract main content
        content_sections = []
        
        # Coverage indications
        coverage_elem = soup.select_one("#coverage-indications, .coverage-section")
        if coverage_elem:
            content_sections.append(f"Coverage Indications:\n{coverage_elem.get_text(strip=True)}")
        
        # Limitations
        limitations_elem = soup.select_one("#limitations, .limitations-section")
        if limitations_elem:
            content_sections.append(f"Limitations:\n{limitations_elem.get_text(strip=True)}")
        
        # If no specific sections found, get main content area
        if not content_sections:
            main_content = soup.select_one("main, .main-content, #content, article")
            if main_content:
                content_sections.append(main_content.get_text(strip=True))
        
        full_content = "\n\n".join(content_sections)
        
        # Create metadata
        metadata = DocumentMetadata(
            document_id=ncd_id,
            document_type=DocumentType.NCD,
            title=title,
            source_url=f"{self.NCD_DETAIL_URL}?ncdId={ncd_id}",
            effective_date=effective_date,
            last_updated=datetime.utcnow(),
        )
        
        # Create chunks
        chunks = self._create_chunks(ncd_id, full_content)
        
        return IngestedDocument(
            metadata=metadata,
            content=full_content,
            chunks=chunks,
        )

    async def _handle_pagination(
        self,
        client: httpx.AsyncClient,
        soup: BeautifulSoup,
        current_results: list[DocumentMetadata],
        limit: int,
        parse_func,
    ) -> list[DocumentMetadata]:
        """Handle pagination for search results."""
        results = current_results.copy()
        
        while len(results) < limit:
            # Find next page link
            next_link = soup.select_one(
                "a.next-page, a[rel='next'], .pagination a:contains('Next')"
            )
            
            if not next_link:
                break
                
            next_url = next_link.get("href")
            if not next_url:
                break
                
            # Make absolute URL
            if not next_url.startswith("http"):
                next_url = urljoin(self.BASE_URL, next_url)
            
            try:
                response = await client.get(next_url)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                
                new_results = parse_func(soup, limit - len(results))
                if not new_results:
                    break
                    
                results.extend(new_results)
                
            except Exception as e:
                logger.warning(f"Error fetching next page: {e}")
                break
        
        return results[:limit]

    def _create_chunks(
        self, document_id: str, content: str
    ) -> list[DocumentChunk]:
        """Create semantic chunks from document content."""
        chunks: list[DocumentChunk] = []
        
        if not content:
            return chunks
        
        # Split by paragraphs first
        paragraphs = re.split(r"\n\n+", content)
        
        current_chunk = ""
        chunk_index = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
                
            # If adding this paragraph exceeds chunk size, save current chunk
            if current_chunk and len(current_chunk) + len(para) > self.chunk_size:
                chunks.append(DocumentChunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index}",
                    document_id=document_id,
                    content=current_chunk.strip(),
                    chunk_index=chunk_index,
                    metadata={"source": "cms.gov"},
                ))
                chunk_index += 1
                current_chunk = para
            else:
                current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        
        # Don't forget the last chunk
        if current_chunk:
            chunks.append(DocumentChunk(
                chunk_id=f"{document_id}_chunk_{chunk_index}",
                document_id=document_id,
                content=current_chunk.strip(),
                chunk_index=chunk_index,
                metadata={"source": "cms.gov"},
            ))
        
        return chunks

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from various formats."""
        date_formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
        ]
        
        date_text = date_text.strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue
        
        return None
