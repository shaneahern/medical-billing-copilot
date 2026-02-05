"""CMS Coverage API client for Medicare LCDs and NCDs.

This module implements the CMS Coverage API client for incremental updates
of Medicare Local Coverage Determinations (LCDs) and National Coverage
Determinations (NCDs).

API Documentation: https://api.coverage.cms.gov
- /v1/reports/local-coverage-final-lcds - Final LCDs (requires license token)
- /v1/reports/local-coverage-proposed-lcds - Proposed LCDs
- /v1/reports/local-coverage-articles - LCD Articles

Requirements: 11.1
"""

import logging
from datetime import datetime
from typing import Optional

import httpx

from src.schemas.ingestion import (
    DocumentChunk,
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
)

logger = logging.getLogger(__name__)


class CMSCoverageAPIClient:
    """Client for CMS Coverage API.
    
    The Coverage API provides programmatic access to Medicare coverage data.
    Note: LCD endpoints require a license agreement token for full access.
    """

    BASE_URL = "https://api.coverage.cms.gov"
    
    # API endpoints
    FINAL_LCDS_ENDPOINT = "/v1/reports/local-coverage-final-lcds"
    PROPOSED_LCDS_ENDPOINT = "/v1/reports/local-coverage-proposed-lcds"
    LCD_ARTICLES_ENDPOINT = "/v1/reports/local-coverage-articles"
    NCDS_ENDPOINT = "/v1/reports/national-coverage-determinations"

    def __init__(
        self,
        license_token: Optional[str] = None,
        timeout: float = 30.0,
        chunk_size: int = 1000,
    ):
        """Initialize the CMS Coverage API client.
        
        Args:
            license_token: License agreement token for LCD access (optional).
            timeout: HTTP request timeout in seconds.
            chunk_size: Target size for document chunks (in characters).
        """
        self.license_token = license_token
        self.timeout = timeout
        self.chunk_size = chunk_size
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None or self._client.is_closed:
            headers = {
                "Accept": "application/json",
                "User-Agent": "MedicalBillingCopilot/1.0",
            }
            if self.license_token:
                headers["Authorization"] = f"Bearer {self.license_token}"
            
            self._client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self.timeout,
                headers=headers,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def fetch_final_lcds(
        self,
        mac_region: Optional[str] = None,
        cpt_code: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IngestedDocument]:
        """Fetch final LCDs from the Coverage API.
        
        Note: This endpoint requires a license agreement token.
        
        Args:
            mac_region: Filter by MAC region/contractor.
            cpt_code: Filter by CPT code.
            limit: Maximum number of results.
            offset: Pagination offset.
            
        Returns:
            List of ingested LCD documents.
        """
        logger.info(f"Fetching final LCDs from Coverage API (mac={mac_region}, cpt={cpt_code})")
        
        params = {"limit": limit, "offset": offset}
        if mac_region:
            params["contractor"] = mac_region
        if cpt_code:
            params["cptCode"] = cpt_code
        
        try:
            client = await self._get_client()
            response = await client.get(self.FINAL_LCDS_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            documents = self._parse_lcd_response(data)
            logger.info(f"Fetched {len(documents)} final LCDs from API")
            return documents
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.warning("LCD API requires license token - access denied")
            elif e.response.status_code == 403:
                logger.warning("LCD API license token invalid or expired")
            else:
                logger.error(f"HTTP error fetching LCDs: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching LCDs from API: {e}")
            return []

    async def fetch_proposed_lcds(
        self,
        mac_region: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IngestedDocument]:
        """Fetch proposed LCDs from the Coverage API.
        
        Args:
            mac_region: Filter by MAC region/contractor.
            limit: Maximum number of results.
            offset: Pagination offset.
            
        Returns:
            List of ingested LCD documents.
        """
        logger.info(f"Fetching proposed LCDs from Coverage API (mac={mac_region})")
        
        params = {"limit": limit, "offset": offset}
        if mac_region:
            params["contractor"] = mac_region
        
        try:
            client = await self._get_client()
            response = await client.get(self.PROPOSED_LCDS_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            documents = self._parse_lcd_response(data, is_proposed=True)
            logger.info(f"Fetched {len(documents)} proposed LCDs from API")
            return documents
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching proposed LCDs: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching proposed LCDs from API: {e}")
            return []

    async def fetch_lcd_articles(
        self,
        mac_region: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[IngestedDocument]:
        """Fetch LCD articles from the Coverage API.
        
        Args:
            mac_region: Filter by MAC region/contractor.
            limit: Maximum number of results.
            offset: Pagination offset.
            
        Returns:
            List of ingested article documents.
        """
        logger.info(f"Fetching LCD articles from Coverage API (mac={mac_region})")
        
        params = {"limit": limit, "offset": offset}
        if mac_region:
            params["contractor"] = mac_region
        
        try:
            client = await self._get_client()
            response = await client.get(self.LCD_ARTICLES_ENDPOINT, params=params)
            response.raise_for_status()
            
            data = response.json()
            documents = self._parse_article_response(data)
            logger.info(f"Fetched {len(documents)} LCD articles from API")
            return documents
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching LCD articles: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching LCD articles from API: {e}")
            return []

    def _parse_lcd_response(
        self, data: dict, is_proposed: bool = False
    ) -> list[IngestedDocument]:
        """Parse LCD API response into IngestedDocuments."""
        documents = []
        
        items = data.get("data", data.get("items", data.get("results", [])))
        if isinstance(items, dict):
            items = [items]
        
        for item in items:
            try:
                lcd_id = item.get("lcdId", item.get("id", ""))
                if not lcd_id:
                    continue
                
                title = item.get("title", item.get("lcdTitle", f"LCD {lcd_id}"))
                contractor = item.get("contractor", item.get("macName", ""))
                
                # Parse effective date
                effective_date = None
                date_str = item.get("effectiveDate", item.get("effective_date"))
                if date_str:
                    try:
                        effective_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                # Build content from available fields
                content_parts = [f"Title: {title}"]
                if contractor:
                    content_parts.append(f"Contractor: {contractor}")
                if item.get("summary"):
                    content_parts.append(f"Summary: {item['summary']}")
                if item.get("coverageIndications"):
                    content_parts.append(f"Coverage Indications: {item['coverageIndications']}")
                if item.get("limitations"):
                    content_parts.append(f"Limitations: {item['limitations']}")
                if item.get("cptCodes"):
                    codes = item["cptCodes"]
                    if isinstance(codes, list):
                        codes = ", ".join(codes)
                    content_parts.append(f"CPT Codes: {codes}")
                
                content = "\n\n".join(content_parts)
                
                # Build source URL
                source_url = f"https://localcoverage.cms.gov/mcd_archive/search-results.aspx?keyword=L{lcd_id}"
                
                metadata = DocumentMetadata(
                    document_id=lcd_id,
                    document_type=DocumentType.LCD,
                    title=title,
                    source_url=source_url,
                    mac_region=contractor,
                    effective_date=effective_date,
                    last_updated=datetime.utcnow(),
                )
                
                chunks = self._create_chunks(lcd_id, content)
                
                documents.append(IngestedDocument(
                    metadata=metadata,
                    content=content,
                    chunks=chunks,
                ))
                
            except Exception as e:
                logger.warning(f"Failed to parse LCD item: {e}")
                continue
        
        return documents

    def _parse_article_response(self, data: dict) -> list[IngestedDocument]:
        """Parse LCD article API response into IngestedDocuments."""
        documents = []
        
        items = data.get("data", data.get("items", data.get("results", [])))
        if isinstance(items, dict):
            items = [items]
        
        for item in items:
            try:
                article_id = item.get("articleId", item.get("id", ""))
                if not article_id:
                    continue
                
                title = item.get("title", item.get("articleTitle", f"Article {article_id}"))
                contractor = item.get("contractor", item.get("macName", ""))
                
                # Parse effective date
                effective_date = None
                date_str = item.get("effectiveDate", item.get("effective_date"))
                if date_str:
                    try:
                        effective_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                
                # Build content
                content_parts = [f"Title: {title}"]
                if contractor:
                    content_parts.append(f"Contractor: {contractor}")
                if item.get("content"):
                    content_parts.append(item["content"])
                
                content = "\n\n".join(content_parts)
                
                metadata = DocumentMetadata(
                    document_id=article_id,
                    document_type=DocumentType.LCD,  # Articles are LCD-related
                    title=title,
                    source_url=item.get("sourceUrl", ""),
                    mac_region=contractor,
                    effective_date=effective_date,
                    last_updated=datetime.utcnow(),
                )
                
                chunks = self._create_chunks(article_id, content)
                
                documents.append(IngestedDocument(
                    metadata=metadata,
                    content=content,
                    chunks=chunks,
                ))
                
            except Exception as e:
                logger.warning(f"Failed to parse article item: {e}")
                continue
        
        return documents

    def _create_chunks(self, document_id: str, content: str) -> list[DocumentChunk]:
        """Create semantic chunks from document content."""
        import re
        
        chunks: list[DocumentChunk] = []
        if not content:
            return chunks
        
        paragraphs = re.split(r"\n\n+", content)
        current_chunk = ""
        chunk_index = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para:
                continue
            
            if current_chunk and len(current_chunk) + len(para) > self.chunk_size:
                chunks.append(DocumentChunk(
                    chunk_id=f"{document_id}_chunk_{chunk_index}",
                    document_id=document_id,
                    content=current_chunk.strip(),
                    chunk_index=chunk_index,
                    metadata={"source": "cms_api"},
                ))
                chunk_index += 1
                current_chunk = para
            else:
                current_chunk = f"{current_chunk}\n\n{para}" if current_chunk else para
        
        if current_chunk:
            chunks.append(DocumentChunk(
                chunk_id=f"{document_id}_chunk_{chunk_index}",
                document_id=document_id,
                content=current_chunk.strip(),
                chunk_index=chunk_index,
                metadata={"source": "cms_api"},
            ))
        
        return chunks
