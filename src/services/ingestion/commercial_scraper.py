"""Commercial payer policy scraper for Medical Billing Copilot.

This module implements web scraping and PDF extraction for commercial payer
policy documents (Aetna, UnitedHealthcare, Cigna, etc.).

Requirements: 11.2
"""

import io
import logging
import re
import uuid
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from src.schemas.ingestion import (
    CommercialPayerConfig,
    DocumentChunk,
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
)

logger = logging.getLogger(__name__)


# Try to import PyPDF2, but make it optional
try:
    from PyPDF2 import PdfReader
    PDF_SUPPORT = True
except ImportError:
    PDF_SUPPORT = False
    logger.warning("PyPDF2 not installed. PDF extraction will be unavailable.")


class CommercialPayerScraper:
    """Scraper for commercial payer policy documents.
    
    This class handles:
    - Scraping HTML policy pages from payer websites
    - Extracting text from PDF policy documents
    - Managing payer-specific configurations
    - Handling authentication when required
    
    Requirements: 11.2
    """

    # Default payer configurations
    DEFAULT_PAYER_CONFIGS = {
        "aetna": CommercialPayerConfig(
            payer_id="aetna",
            payer_name="Aetna",
            base_url="https://www.aetna.com",
            policy_list_url="https://www.aetna.com/health-care-professionals/clinical-policy-bulletins.html",
            requires_auth=False,
            scrape_method="html",
        ),
        "unitedhealthcare": CommercialPayerConfig(
            payer_id="unitedhealthcare",
            payer_name="UnitedHealthcare",
            base_url="https://www.uhcprovider.com",
            policy_list_url="https://www.uhcprovider.com/en/policies-protocols/commercial-policies.html",
            requires_auth=False,
            scrape_method="html",
        ),
        "cigna": CommercialPayerConfig(
            payer_id="cigna",
            payer_name="Cigna",
            base_url="https://www.cigna.com",
            policy_list_url="https://www.cigna.com/health-care-providers/coverage-and-claims/coverage-policies",
            requires_auth=False,
            scrape_method="html",
        ),
        "humana": CommercialPayerConfig(
            payer_id="humana",
            payer_name="Humana",
            base_url="https://www.humana.com",
            policy_list_url="https://www.humana.com/provider/medical-resources/clinical-policies",
            requires_auth=False,
            scrape_method="html",
        ),
        "anthem": CommercialPayerConfig(
            payer_id="anthem",
            payer_name="Anthem",
            base_url="https://www.anthem.com",
            policy_list_url="https://www.anthem.com/provider/policies",
            requires_auth=False,
            scrape_method="html",
        ),
    }

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        chunk_size: int = 1000,
        custom_configs: Optional[dict[str, CommercialPayerConfig]] = None,
    ):
        """Initialize the commercial payer scraper.
        
        Args:
            timeout: HTTP request timeout in seconds.
            max_retries: Maximum number of retry attempts.
            chunk_size: Target size for document chunks (in characters).
            custom_configs: Custom payer configurations to override defaults.
        """
        self.timeout = timeout
        self.max_retries = max_retries
        self.chunk_size = chunk_size
        self._client: Optional[httpx.AsyncClient] = None
        
        # Merge custom configs with defaults
        self.payer_configs = self.DEFAULT_PAYER_CONFIGS.copy()
        if custom_configs:
            self.payer_configs.update(custom_configs)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "MedicalBillingCopilot/1.0 (Policy Research Bot)",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/pdf",
                    "Accept-Language": "en-US,en;q=0.9",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def get_supported_payers(self) -> list[str]:
        """Get list of supported payer IDs."""
        return list(self.payer_configs.keys())

    def get_payer_config(self, payer_id: str) -> Optional[CommercialPayerConfig]:
        """Get configuration for a specific payer."""
        return self.payer_configs.get(payer_id.lower())

    async def scrape_payer_policies(
        self, payer_id: str, limit: int = 100
    ) -> list[IngestedDocument]:
        """Scrape all policies for a specific payer.
        
        Args:
            payer_id: The payer identifier.
            limit: Maximum number of policies to scrape.
            
        Returns:
            List of ingested policy documents.
        """
        config = self.get_payer_config(payer_id)
        if not config:
            raise ValueError(f"Unknown payer: {payer_id}")
        
        logger.info(f"Scraping policies for {config.payer_name}")
        
        # Get list of policy URLs
        policy_urls = await self._get_policy_list(config, limit)
        
        # Scrape each policy
        documents: list[IngestedDocument] = []
        for url in policy_urls:
            try:
                if config.scrape_method == "pdf" or url.lower().endswith(".pdf"):
                    document = await self.extract_pdf_policy(url, config)
                else:
                    document = await self.scrape_html_policy(url, config)
                documents.append(document)
            except Exception as e:
                logger.error(f"Failed to scrape policy {url}: {e}")
                continue
        
        logger.info(f"Scraped {len(documents)} policies for {config.payer_name}")
        return documents

    async def scrape_html_policy(
        self, url: str, config: CommercialPayerConfig
    ) -> IngestedDocument:
        """Scrape a policy from an HTML page.
        
        Args:
            url: URL of the policy page.
            config: Payer configuration.
            
        Returns:
            IngestedDocument with extracted content.
        """
        logger.info(f"Scraping HTML policy: {url}")
        
        client = await self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Extract title
        title = self._extract_title(soup)
        
        # Extract main content
        content = self._extract_html_content(soup)
        
        # Extract effective date
        effective_date = self._extract_effective_date(soup)
        
        # Generate document ID
        doc_id = self._generate_document_id(config.payer_id, url)
        
        # Create metadata
        metadata = DocumentMetadata(
            document_id=doc_id,
            document_type=DocumentType.COMMERCIAL,
            title=title,
            source_url=url,
            payer=config.payer_name,
            effective_date=effective_date,
            last_updated=datetime.utcnow(),
        )
        
        # Create chunks
        chunks = self._create_chunks(doc_id, content)
        
        return IngestedDocument(
            metadata=metadata,
            content=content,
            chunks=chunks,
        )

    async def extract_pdf_policy(
        self, url: str, config: CommercialPayerConfig
    ) -> IngestedDocument:
        """Extract policy content from a PDF document.
        
        Args:
            url: URL of the PDF document.
            config: Payer configuration.
            
        Returns:
            IngestedDocument with extracted content.
        """
        if not PDF_SUPPORT:
            raise RuntimeError("PDF extraction requires PyPDF2. Install with: pip install pypdf2")
        
        logger.info(f"Extracting PDF policy: {url}")
        
        client = await self._get_client()
        response = await client.get(url)
        response.raise_for_status()
        
        # Parse PDF
        pdf_content = io.BytesIO(response.content)
        reader = PdfReader(pdf_content)
        
        # Extract text from all pages
        text_parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        content = "\n\n".join(text_parts)
        
        # Extract title from first page or filename
        title = self._extract_pdf_title(reader, url)
        
        # Generate document ID
        doc_id = self._generate_document_id(config.payer_id, url)
        
        # Create metadata
        metadata = DocumentMetadata(
            document_id=doc_id,
            document_type=DocumentType.COMMERCIAL,
            title=title,
            source_url=url,
            payer=config.payer_name,
            last_updated=datetime.utcnow(),
        )
        
        # Create chunks
        chunks = self._create_chunks(doc_id, content)
        
        return IngestedDocument(
            metadata=metadata,
            content=content,
            chunks=chunks,
        )

    async def extract_pdf_from_bytes(
        self, pdf_bytes: bytes, payer_name: str, title: str, source_url: str = ""
    ) -> IngestedDocument:
        """Extract policy content from PDF bytes.
        
        Args:
            pdf_bytes: Raw PDF content.
            payer_name: Name of the payer.
            title: Document title.
            source_url: Optional source URL.
            
        Returns:
            IngestedDocument with extracted content.
        """
        if not PDF_SUPPORT:
            raise RuntimeError("PDF extraction requires PyPDF2. Install with: pip install pypdf2")
        
        logger.info(f"Extracting PDF: {title}")
        
        # Parse PDF
        pdf_content = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_content)
        
        # Extract text from all pages
        text_parts: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        
        content = "\n\n".join(text_parts)
        
        # Generate document ID
        doc_id = str(uuid.uuid4())[:8]
        
        # Create metadata
        metadata = DocumentMetadata(
            document_id=doc_id,
            document_type=DocumentType.COMMERCIAL,
            title=title,
            source_url=source_url,
            payer=payer_name,
            last_updated=datetime.utcnow(),
        )
        
        # Create chunks
        chunks = self._create_chunks(doc_id, content)
        
        return IngestedDocument(
            metadata=metadata,
            content=content,
            chunks=chunks,
        )

    async def _get_policy_list(
        self, config: CommercialPayerConfig, limit: int
    ) -> list[str]:
        """Get list of policy URLs from payer's policy listing page."""
        if not config.policy_list_url:
            return []
        
        client = await self._get_client()
        
        try:
            response = await client.get(config.policy_list_url)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch policy list for {config.payer_name}: {e}")
            return []
        
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find policy links
        policy_urls: list[str] = []
        
        # Common selectors for policy links
        selectors = [
            "a[href*='policy']",
            "a[href*='bulletin']",
            "a[href*='coverage']",
            ".policy-link a",
            ".bulletin-link a",
            "table.policies a",
            ".policy-list a",
        ]
        
        for selector in selectors:
            links = soup.select(selector)
            for link in links:
                href = link.get("href")
                if href:
                    # Make absolute URL
                    if not href.startswith("http"):
                        href = urljoin(config.base_url, href)
                    if href not in policy_urls:
                        policy_urls.append(href)
                        if len(policy_urls) >= limit:
                            break
            if len(policy_urls) >= limit:
                break
        
        return policy_urls[:limit]

    def _extract_title(self, soup: BeautifulSoup) -> str:
        """Extract document title from HTML."""
        # Try various title selectors
        selectors = [
            "h1",
            ".policy-title",
            ".document-title",
            "title",
            "[data-title]",
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                title = elem.get_text(strip=True)
                if title and len(title) > 5:
                    return title
        
        return "Untitled Policy"

    def _extract_html_content(self, soup: BeautifulSoup) -> str:
        """Extract main content from HTML page."""
        # Remove script and style elements
        for element in soup(["script", "style", "nav", "header", "footer"]):
            element.decompose()
        
        # Try to find main content area
        content_selectors = [
            "main",
            "article",
            ".policy-content",
            ".document-content",
            "#content",
            ".main-content",
        ]
        
        for selector in content_selectors:
            content_elem = soup.select_one(selector)
            if content_elem:
                return content_elem.get_text(separator="\n", strip=True)
        
        # Fall back to body
        body = soup.find("body")
        if body:
            return body.get_text(separator="\n", strip=True)
        
        return soup.get_text(separator="\n", strip=True)

    def _extract_effective_date(self, soup: BeautifulSoup) -> Optional[datetime]:
        """Extract effective date from HTML page."""
        # Common date selectors
        selectors = [
            ".effective-date",
            ".policy-date",
            "[data-effective-date]",
            ".date",
        ]
        
        for selector in selectors:
            elem = soup.select_one(selector)
            if elem:
                date_text = elem.get_text(strip=True)
                parsed = self._parse_date(date_text)
                if parsed:
                    return parsed
        
        # Try to find date in text
        text = soup.get_text()
        date_patterns = [
            r"Effective[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
            r"Effective[:\s]+(\w+ \d{1,2}, \d{4})",
            r"Last Updated[:\s]+(\d{1,2}/\d{1,2}/\d{4})",
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                parsed = self._parse_date(match.group(1))
                if parsed:
                    return parsed
        
        return None

    def _extract_pdf_title(self, reader: "PdfReader", url: str) -> str:
        """Extract title from PDF metadata or filename."""
        # Try PDF metadata
        if reader.metadata:
            title = reader.metadata.get("/Title")
            if title and len(str(title)) > 5:
                return str(title)
        
        # Try first page content
        if reader.pages:
            first_page = reader.pages[0].extract_text()
            if first_page:
                lines = first_page.split("\n")
                for line in lines[:5]:
                    line = line.strip()
                    if len(line) > 10 and len(line) < 200:
                        return line
        
        # Fall back to filename
        parsed = urlparse(url)
        filename = parsed.path.split("/")[-1]
        if filename:
            return filename.replace(".pdf", "").replace("-", " ").replace("_", " ")
        
        return "Untitled Policy"

    def _generate_document_id(self, payer_id: str, url: str) -> str:
        """Generate a unique document ID."""
        # Use URL hash for consistency
        url_hash = str(hash(url))[-8:]
        return f"{payer_id}_{url_hash}"

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
                    metadata={"source": "commercial_payer"},
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
                metadata={"source": "commercial_payer"},
            ))
        
        return chunks

    def _parse_date(self, date_text: str) -> Optional[datetime]:
        """Parse date from various formats."""
        date_formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%b %d, %Y",
            "%m-%d-%Y",
        ]
        
        date_text = date_text.strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_text, fmt)
            except ValueError:
                continue
        
        return None
