"""CMS Medicare Coverage Database Downloads parser.

This module implements parsing of bulk download files from the CMS Medicare
Coverage Database (MCD) for initial data load.

Download Source: https://www.cms.gov/medicare-coverage-database/downloads/downloads.aspx
- LCD ZIP files with CSV data
- NCD ZIP files with CSV data
- Updated weekly, requires accepting license agreement

Note: The MCD downloads page uses JavaScript to generate download links dynamically
after accepting license agreements. Direct download URLs may change frequently.
This parser attempts to discover URLs dynamically and falls back to known patterns.

Requirements: 11.1
"""

import csv
import io
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from bs4 import BeautifulSoup

from src.schemas.ingestion import (
    DocumentChunk,
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
)

logger = logging.getLogger(__name__)

# Increase CSV field size limit for large CMS documents
csv.field_size_limit(10 * 1024 * 1024)  # 10 MB limit


class CMSDownloadsParser:
    """Parser for CMS Medicare Coverage Database bulk downloads.
    
    The MCD Downloads provide bulk ZIP files containing CSV/Access DB files
    for LCDs, NCDs, and Articles. Updated weekly.
    
    Note: CMS download URLs change frequently and require license acceptance.
    This parser attempts multiple URL patterns and falls back gracefully.
    """

    DOWNLOADS_PAGE_URL = "https://www.cms.gov/medicare-coverage-database/downloads/downloads.aspx"
    
    # Multiple URL patterns to try (CMS changes these periodically)
    LCD_URL_PATTERNS = [
        "https://www.cms.gov/medicare-coverage-database/downloads/lcd-data.zip",
        "https://www.cms.gov/medicare-coverage-database/downloads/current-lcd-data.zip",
        "https://www.cms.gov/files/zip/lcd-database.zip",
        "https://www.cms.gov/files/zip/lcd-data.zip",
        "https://www.cms.gov/files/zip/mcd-lcd-data.zip",
    ]
    
    NCD_URL_PATTERNS = [
        "https://www.cms.gov/medicare-coverage-database/downloads/ncd-data.zip",
        "https://www.cms.gov/medicare-coverage-database/downloads/current-ncd-data.zip",
        "https://www.cms.gov/files/zip/ncd-database.zip",
        "https://www.cms.gov/files/zip/ncd-data.zip",
        "https://www.cms.gov/files/zip/mcd-ncd-data.zip",
    ]
    
    ARTICLE_URL_PATTERNS = [
        "https://www.cms.gov/medicare-coverage-database/downloads/article-data.zip",
        "https://www.cms.gov/files/zip/article-database.zip",
    ]

    def __init__(
        self,
        download_dir: str = "data/cms_downloads",
        timeout: float = 120.0,
        chunk_size: int = 1000,
    ):
        """Initialize the CMS Downloads parser.
        
        Args:
            download_dir: Directory to store downloaded files.
            timeout: HTTP request timeout in seconds.
            chunk_size: Target size for document chunks (in characters).
        """
        self.download_dir = Path(download_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = timeout
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
                    "Accept": "*/*",
                },
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _discover_download_urls(self) -> dict[str, str]:
        """Attempt to discover download URLs from the MCD downloads page.
        
        Returns:
            Dict mapping data type to URL (e.g., {"lcd": "https://...", "ncd": "https://..."})
        """
        discovered = {}
        
        try:
            client = await self._get_client()
            response = await client.get(self.DOWNLOADS_PAGE_URL)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            
            # Look for download links in the page
            for link in soup.find_all("a", href=True):
                href = link.get("href", "").lower()
                link_text = link.get_text(strip=True).lower()
                
                # Check for LCD download links
                if "lcd" in href or "lcd" in link_text:
                    if ".zip" in href:
                        discovered["lcd"] = link["href"]
                        logger.info(f"Discovered LCD download URL: {link['href']}")
                
                # Check for NCD download links
                if "ncd" in href or "ncd" in link_text:
                    if ".zip" in href:
                        discovered["ncd"] = link["href"]
                        logger.info(f"Discovered NCD download URL: {link['href']}")
                        
        except Exception as e:
            logger.warning(f"Could not discover download URLs from page: {e}")
        
        return discovered

    async def _try_download(self, urls: list[str]) -> Optional[bytes]:
        """Try downloading from multiple URLs until one succeeds.
        
        Args:
            urls: List of URLs to try in order.
            
        Returns:
            Downloaded content bytes, or None if all URLs failed.
        """
        client = await self._get_client()
        
        for url in urls:
            try:
                logger.info(f"Trying download URL: {url}")
                response = await client.get(url)
                response.raise_for_status()
                logger.info(f"Successfully downloaded from: {url}")
                return response.content
            except httpx.HTTPStatusError as e:
                logger.warning(f"HTTP {e.response.status_code} for {url}")
                continue
            except Exception as e:
                logger.warning(f"Error downloading from {url}: {e}")
                continue
        
        return None

    async def download_and_parse_lcds(self) -> list[IngestedDocument]:
        """Download and parse LCD bulk data.
        
        Tries multiple URL patterns and falls back gracefully.
        
        Returns:
            List of ingested LCD documents.
        """
        logger.info("Downloading LCD bulk data from CMS...")
        
        # First try to discover URLs from the downloads page
        discovered = await self._discover_download_urls()
        
        # Build list of URLs to try
        urls_to_try = []
        if "lcd" in discovered:
            urls_to_try.append(discovered["lcd"])
        urls_to_try.extend(self.LCD_URL_PATTERNS)
        
        # Try downloading
        content = await self._try_download(urls_to_try)
        
        if content:
            documents = self._parse_lcd_zip(content)
            logger.info(f"Parsed {len(documents)} LCDs from bulk download")
            return documents
        
        logger.error("All LCD download URLs failed - bulk download not available")
        logger.info("Note: CMS MCD downloads require accepting license agreements via browser")
        logger.info("Consider using the Coverage API or stub data as alternatives")
        return []

    async def download_and_parse_ncds(self) -> list[IngestedDocument]:
        """Download and parse NCD bulk data.
        
        Tries multiple URL patterns and falls back gracefully.
        
        Returns:
            List of ingested NCD documents.
        """
        logger.info("Downloading NCD bulk data from CMS...")
        
        # First try to discover URLs from the downloads page
        discovered = await self._discover_download_urls()
        
        # Build list of URLs to try
        urls_to_try = []
        if "ncd" in discovered:
            urls_to_try.append(discovered["ncd"])
        urls_to_try.extend(self.NCD_URL_PATTERNS)
        
        # Try downloading
        content = await self._try_download(urls_to_try)
        
        if content:
            documents = self._parse_ncd_zip(content)
            logger.info(f"Parsed {len(documents)} NCDs from bulk download")
            return documents
        
        logger.error("All NCD download URLs failed - bulk download not available")
        logger.info("Note: CMS MCD downloads require accepting license agreements via browser")
        logger.info("Consider using the Coverage API or stub data as alternatives")
        return []

    def _parse_lcd_zip(self, zip_content: bytes) -> list[IngestedDocument]:
        """Parse LCD ZIP file content.
        
        Handles nested ZIP structure (e.g., all_lcd.zip contains all_lcd_csv.zip).
        Also parses lcd_x_contractor.csv to map LCDs to MAC regions.
        """
        documents = []
        contractor_mapping: dict[str, str] = {}  # lcd_id -> contractor name
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                # Look for CSV files or nested ZIP files
                for filename in zf.namelist():
                    logger.info(f"Found file in ZIP: {filename}")
                    
                    # Handle nested ZIP files (e.g., all_lcd_csv.zip)
                    if filename.lower().endswith('.zip') and 'csv' in filename.lower():
                        logger.info(f"Processing nested CSV ZIP: {filename}")
                        try:
                            with zf.open(filename) as nested_zip_file:
                                nested_content = nested_zip_file.read()
                                docs, mapping = self._parse_nested_lcd_csv_zip(nested_content)
                                documents.extend(docs)
                                contractor_mapping.update(mapping)
                        except Exception as e:
                            logger.warning(f"Error processing nested ZIP {filename}: {e}")
                            continue
                    
                    # Handle direct CSV files
                    elif filename.lower().endswith('.csv'):
                        logger.info(f"Processing LCD CSV file: {filename}")
                        try:
                            with zf.open(filename) as f:
                                content = self._decode_file_content(f.read())
                                if content:
                                    if 'contractor' in filename.lower():
                                        mapping = self._parse_contractor_csv(content)
                                        contractor_mapping.update(mapping)
                                    else:
                                        docs = self._parse_lcd_csv(content, filename)
                                        documents.extend(docs)
                        except Exception as e:
                            logger.warning(f"Error processing {filename}: {e}")
                            continue
            
            # Apply contractor mapping to documents
            if contractor_mapping:
                logger.info(f"Applying contractor mapping to {len(documents)} LCDs ({len(contractor_mapping)} mappings)")
                for doc in documents:
                    lcd_id = doc.metadata.document_id
                    if lcd_id in contractor_mapping:
                        mac_region = self._normalize_mac_region(contractor_mapping[lcd_id])
                        doc.metadata.mac_region = mac_region
                        
        except zipfile.BadZipFile:
            logger.error("Invalid ZIP file received")
        except Exception as e:
            logger.error(f"Error parsing LCD ZIP: {e}")
        
        return documents

    def _parse_nested_lcd_csv_zip(self, zip_content: bytes) -> tuple[list[IngestedDocument], dict[str, str]]:
        """Parse a nested ZIP file containing LCD CSV files.
        
        Returns:
            Tuple of (documents, contractor_mapping)
        """
        documents = []
        contractor_mapping: dict[str, str] = {}
        contractor_names: dict[str, str] = {}  # contractor_id -> contractor_name
        lcd_to_contractor_id: dict[str, str] = {}  # lcd_id -> contractor_id
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                csv_files = [f for f in zf.namelist() if f.lower().endswith('.csv')]
                logger.info(f"Found {len(csv_files)} CSV files in nested ZIP: {csv_files}")
                
                # First pass: parse contractor names (contractor.csv)
                for csv_file in csv_files:
                    if csv_file.lower() == 'contractor.csv':
                        try:
                            with zf.open(csv_file) as f:
                                content = self._decode_file_content(f.read())
                                if content:
                                    contractor_names = self._parse_contractor_names_csv(content)
                                    logger.info(f"Loaded {len(contractor_names)} contractor names from {csv_file}")
                        except Exception as e:
                            logger.warning(f"Error processing contractor names file {csv_file}: {e}")
                
                # Second pass: parse LCD-to-contractor mapping (lcd_x_contractor.csv)
                for csv_file in csv_files:
                    if 'lcd_x_contractor' in csv_file.lower() or 'x_contractor' in csv_file.lower():
                        try:
                            with zf.open(csv_file) as f:
                                content = self._decode_file_content(f.read())
                                if content:
                                    lcd_to_contractor_id = self._parse_lcd_contractor_mapping_csv(content)
                                    logger.info(f"Loaded {len(lcd_to_contractor_id)} LCD-to-contractor mappings from {csv_file}")
                        except Exception as e:
                            logger.warning(f"Error processing LCD-contractor mapping file {csv_file}: {e}")
                
                # Build final mapping: lcd_id -> contractor_name
                for lcd_id, contractor_id in lcd_to_contractor_id.items():
                    if contractor_id in contractor_names:
                        contractor_mapping[lcd_id] = contractor_names[contractor_id]
                    else:
                        # Use contractor_id as fallback
                        contractor_mapping[lcd_id] = contractor_id
                
                if contractor_mapping:
                    logger.info(f"Built {len(contractor_mapping)} LCD-to-contractor-name mappings")
                else:
                    logger.warning("No contractor mapping could be built. MAC regions will be UNKNOWN.")
                
                # Third pass: parse LCD documents
                for csv_file in csv_files:
                    if csv_file.lower() == 'lcd.csv':
                        try:
                            with zf.open(csv_file) as f:
                                content = self._decode_file_content(f.read())
                                if content:
                                    docs = self._parse_lcd_csv(content, csv_file)
                                    documents.extend(docs)
                        except Exception as e:
                            logger.warning(f"Error processing {csv_file}: {e}")
                            continue
                        
        except zipfile.BadZipFile:
            logger.error("Invalid nested ZIP file")
        except Exception as e:
            logger.error(f"Error parsing nested ZIP: {e}")
        
        return documents, contractor_mapping

    def _parse_contractor_names_csv(self, csv_content: str) -> dict[str, str]:
        """Parse contractor.csv to get contractor_id -> contractor_name mapping."""
        mapping: dict[str, str] = {}
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            
            if reader.fieldnames:
                logger.info(f"Contractor names CSV columns: {reader.fieldnames}")
            
            for row in reader:
                try:
                    contractor_id = (
                        row.get("contractor_id") or row.get("CONTRACTOR_ID") or
                        row.get("ContractorId") or row.get("id") or ""
                    ).strip()
                    
                    contractor_name = (
                        row.get("contractor_name") or row.get("CONTRACTOR_NAME") or
                        row.get("ContractorName") or row.get("name") or ""
                    ).strip()
                    
                    if contractor_id and contractor_name:
                        mapping[contractor_id] = contractor_name
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing contractor names CSV: {e}")
        
        return mapping

    def _parse_lcd_contractor_mapping_csv(self, csv_content: str) -> dict[str, str]:
        """Parse lcd_x_contractor.csv to get lcd_id -> contractor_id mapping."""
        mapping: dict[str, str] = {}
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            
            if reader.fieldnames:
                logger.info(f"LCD-contractor mapping CSV columns: {reader.fieldnames}")
            
            for row in reader:
                try:
                    lcd_id = (
                        row.get("lcd_id") or row.get("LCD_ID") or
                        row.get("LcdId") or ""
                    ).strip()
                    
                    contractor_id = (
                        row.get("contractor_id") or row.get("CONTRACTOR_ID") or
                        row.get("ContractorId") or ""
                    ).strip()
                    
                    if lcd_id and contractor_id:
                        mapping[lcd_id] = contractor_id
                        
                except Exception as e:
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing LCD-contractor mapping CSV: {e}")
        
        return mapping

    def _parse_contractor_csv(self, csv_content: str) -> dict[str, str]:
        """Parse LCD-to-contractor mapping CSV.
        
        Returns:
            Dict mapping lcd_id to contractor name.
        """
        mapping: dict[str, str] = {}
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            
            # Log available columns for debugging
            if reader.fieldnames:
                logger.info(f"Contractor CSV columns: {reader.fieldnames}")
            
            for row in reader:
                try:
                    lcd_id = (
                        row.get("lcd_id") or row.get("LCD_ID") or row.get("LcdId") or
                        row.get("lcd_num") or row.get("LCD_NUM") or ""
                    ).strip()
                    
                    contractor = (
                        row.get("contractor_name") or row.get("CONTRACTOR_NAME") or
                        row.get("ContractorName") or row.get("contractor") or
                        row.get("CONTRACTOR") or row.get("mac_name") or
                        row.get("MAC_NAME") or row.get("jurisdiction") or ""
                    ).strip()
                    
                    if lcd_id and contractor:
                        mapping[lcd_id] = contractor
                        
                except Exception as e:
                    logger.warning(f"Error parsing contractor row: {e}")
                    continue
            
            logger.info(f"Parsed {len(mapping)} LCD-to-contractor mappings")
                    
        except Exception as e:
            logger.error(f"Error parsing contractor CSV: {e}")
        
        return mapping

    def _normalize_mac_region(self, contractor_name_or_id: str) -> str:
        """Normalize contractor name or ID to MAC region identifier.
        
        Maps contractor names and IDs to standard MAC region codes.
        """
        contractor_lower = contractor_name_or_id.lower().strip()
        
        # CMS Contractor IDs to MAC region mapping
        # Based on CMS Medicare Administrative Contractor (MAC) assignments
        contractor_id_mappings = {
            # Novitas Solutions (JH, JL)
            "240": "NOVITAS", "12501": "NOVITAS", "12502": "NOVITAS",
            # Palmetto GBA (JM, J11)
            "372": "PALMETTO", "11501": "PALMETTO", "11502": "PALMETTO",
            # CGS Administrators (J15)
            "389": "CGS", "15501": "CGS", "15502": "CGS",
            # WPS Government Health Administrators (J5, J8)
            "308": "WPS", "05501": "WPS", "05502": "WPS", "08501": "WPS", "08502": "WPS",
            # National Government Services (J6, JK)
            "313": "NGS", "06501": "NGS", "06502": "NGS",
            # First Coast Service Options (J9, JN)
            "396": "FIRST_COAST", "09501": "FIRST_COAST", "09502": "FIRST_COAST",
            # Noridian Healthcare Solutions (JA, JB, JE, JF)
            "236": "NORIDIAN", "359": "NORIDIAN", "367": "NORIDIAN", "268": "NORIDIAN",
            "373": "NORIDIAN", "339": "NORIDIAN", "338": "NORIDIAN", "143": "NORIDIAN",
            "393": "NORIDIAN", "369": "NORIDIAN",
        }
        
        # Check if it's a contractor ID
        if contractor_name_or_id in contractor_id_mappings:
            return contractor_id_mappings[contractor_name_or_id]
        
        # Map common contractor names to MAC region codes
        mac_name_mappings = {
            "novitas": "NOVITAS",
            "palmetto": "PALMETTO",
            "cgs": "CGS",
            "wps": "WPS",
            "national government services": "NGS",
            "ngs": "NGS",
            "first coast": "FIRST_COAST",
            "noridian": "NORIDIAN",
            "wisconsin physicians service": "WPS",
            "cahaba": "PALMETTO",  # Cahaba merged with Palmetto
        }
        
        for key, value in mac_name_mappings.items():
            if key in contractor_lower:
                return value
        
        # If no match, return cleaned contractor name/ID
        return contractor_name_or_id.upper().replace(" ", "_")[:20]

    def _parse_ncd_zip(self, zip_content: bytes) -> list[IngestedDocument]:
        """Parse NCD ZIP file content.
        
        Handles nested ZIP structure.
        """
        documents = []
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                for filename in zf.namelist():
                    logger.info(f"Found file in ZIP: {filename}")
                    
                    # Handle nested ZIP files
                    if filename.lower().endswith('.zip') and 'csv' in filename.lower():
                        logger.info(f"Processing nested CSV ZIP: {filename}")
                        try:
                            with zf.open(filename) as nested_zip_file:
                                nested_content = nested_zip_file.read()
                                docs = self._parse_nested_csv_zip(nested_content, "ncd")
                                documents.extend(docs)
                        except Exception as e:
                            logger.warning(f"Error processing nested ZIP {filename}: {e}")
                            continue
                    
                    # Handle direct CSV files
                    elif filename.lower().endswith('.csv'):
                        logger.info(f"Processing NCD CSV file: {filename}")
                        try:
                            with zf.open(filename) as f:
                                content = self._decode_file_content(f.read())
                                if content:
                                    docs = self._parse_ncd_csv(content, filename)
                                    documents.extend(docs)
                        except Exception as e:
                            logger.warning(f"Error processing {filename}: {e}")
                            continue
                        
        except zipfile.BadZipFile:
            logger.error("Invalid ZIP file received")
        except Exception as e:
            logger.error(f"Error parsing NCD ZIP: {e}")
        
        return documents

    def _parse_nested_csv_zip(self, zip_content: bytes, doc_type: str) -> list[IngestedDocument]:
        """Parse a nested ZIP file containing CSV files."""
        documents = []
        
        try:
            with zipfile.ZipFile(io.BytesIO(zip_content)) as zf:
                csv_files = [f for f in zf.namelist() if f.lower().endswith('.csv')]
                logger.info(f"Found {len(csv_files)} CSV files in nested ZIP")
                
                for csv_file in csv_files:
                    try:
                        with zf.open(csv_file) as f:
                            content = self._decode_file_content(f.read())
                            if content:
                                if doc_type == "lcd":
                                    docs = self._parse_lcd_csv(content, csv_file)
                                else:
                                    docs = self._parse_ncd_csv(content, csv_file)
                                documents.extend(docs)
                    except Exception as e:
                        logger.warning(f"Error processing {csv_file}: {e}")
                        continue
                        
        except zipfile.BadZipFile:
            logger.error("Invalid nested ZIP file")
        except Exception as e:
            logger.error(f"Error parsing nested ZIP: {e}")
        
        return documents

    def _decode_file_content(self, content: bytes) -> Optional[str]:
        """Try to decode file content with various encodings."""
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                return content.decode(encoding)
            except UnicodeDecodeError:
                continue
        logger.warning("Could not decode file content with any encoding")
        return None

    def _parse_lcd_csv(self, csv_content: str, filename: str = "") -> list[IngestedDocument]:
        """Parse LCD CSV content into documents.
        
        Handles the CMS LCD CSV format with various column names.
        """
        documents = []
        
        # Skip non-LCD files based on filename
        filename_lower = filename.lower()
        
        # Only process the main lcd.csv file
        if filename and filename_lower != 'lcd.csv':
            logger.debug(f"Skipping non-main LCD file: {filename}")
            return documents
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            row_count = 0
            
            # Log columns on first file for debugging
            if reader.fieldnames:
                logger.info(f"LCD CSV columns: {reader.fieldnames[:20]}...")
            
            for row in reader:
                try:
                    # Get LCD ID - the main identifier
                    lcd_id = (
                        row.get("lcd_id") or 
                        row.get("LCD_ID") or 
                        row.get("LcdId") or
                        ""
                    ).strip()
                    
                    if not lcd_id:
                        continue
                    
                    # Get title
                    title = (
                        row.get("title") or 
                        row.get("LCD_TITLE") or 
                        row.get("Title") or
                        f"LCD {lcd_id}"
                    ).strip()
                    
                    # Parse effective date (orig_det_eff_date or rev_eff_date)
                    effective_date = None
                    date_str = (
                        row.get("rev_eff_date") or
                        row.get("orig_det_eff_date") or
                        row.get("EFFECTIVE_DATE") or
                        ""
                    ).strip()
                    if date_str:
                        effective_date = self._parse_date(date_str)
                    
                    # Build content from available fields
                    content_parts = [f"LCD ID: {lcd_id}", f"Title: {title}"]
                    
                    # Add coverage indications
                    indication = (
                        row.get("indication") or
                        row.get("COVERAGE_INDICATIONS") or
                        ""
                    ).strip()
                    if indication:
                        # Clean HTML tags
                        indication = self._clean_html(indication)
                        content_parts.append(f"Coverage Indications:\n{indication}")
                    
                    # Add diagnoses support (ICD codes)
                    diagnoses = (
                        row.get("diagnoses_support") or
                        row.get("DIAGNOSES_SUPPORT") or
                        ""
                    ).strip()
                    if diagnoses:
                        diagnoses = self._clean_html(diagnoses)
                        content_parts.append(f"Diagnoses Support:\n{diagnoses}")
                    
                    # Add coding guidelines
                    coding = (
                        row.get("coding_guidelines") or
                        row.get("CODING_GUIDELINES") or
                        ""
                    ).strip()
                    if coding:
                        coding = self._clean_html(coding)
                        content_parts.append(f"Coding Guidelines:\n{coding}")
                    
                    # Add documentation requirements
                    doc_reqs = (
                        row.get("doc_reqs") or
                        row.get("DOC_REQS") or
                        ""
                    ).strip()
                    if doc_reqs:
                        doc_reqs = self._clean_html(doc_reqs)
                        content_parts.append(f"Documentation Requirements:\n{doc_reqs}")
                    
                    # Add utilization guidelines
                    util_guide = (
                        row.get("util_guide") or
                        row.get("UTIL_GUIDE") or
                        ""
                    ).strip()
                    if util_guide:
                        util_guide = self._clean_html(util_guide)
                        content_parts.append(f"Utilization Guidelines:\n{util_guide}")
                    
                    content = "\n\n".join(content_parts)
                    
                    # Build source URL
                    source_url = f"https://www.cms.gov/medicare-coverage-database/view/lcd.aspx?lcdid={lcd_id}"
                    
                    metadata = DocumentMetadata(
                        document_id=lcd_id,
                        document_type=DocumentType.LCD,
                        title=title,
                        source_url=source_url,
                        mac_region=None,  # Will be populated from lcd_x_contractor.csv if needed
                        effective_date=effective_date,
                        last_updated=datetime.utcnow(),
                    )
                    
                    chunks = self._create_chunks(lcd_id, content)
                    
                    documents.append(IngestedDocument(
                        metadata=metadata,
                        content=content,
                        chunks=chunks,
                    ))
                    row_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error parsing LCD row: {e}")
                    continue
            
            logger.info(f"Parsed {row_count} LCDs from {filename or 'csv content'}")
                    
        except Exception as e:
            logger.error(f"Error parsing LCD CSV: {e}")
        
        return documents

    def _clean_html(self, text: str) -> str:
        """Remove HTML tags and clean up text."""
        if not text:
            return text
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', text)
        # Decode HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")
        text = text.replace('&rsquo;', "'")
        text = text.replace('&ldquo;', '"')
        text = text.replace('&rdquo;', '"')
        text = text.replace('&ndash;', '-')
        text = text.replace('&mdash;', '-')
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            
            for row in reader:
                try:
                    # Try various column name patterns
                    lcd_id = (
                        row.get("LCD_ID") or 
                        row.get("LcdId") or 
                        row.get("lcd_id") or
                        row.get("ID") or
                        ""
                    ).strip()
                    
                    if not lcd_id:
                        continue
                    
                    title = (
                        row.get("LCD_TITLE") or 
                        row.get("LcdTitle") or 
                        row.get("Title") or
                        row.get("title") or
                        f"LCD {lcd_id}"
                    ).strip()
                    
                    contractor = (
                        row.get("CONTRACTOR_NAME") or
                        row.get("ContractorName") or
                        row.get("Contractor") or
                        row.get("MAC_NAME") or
                        ""
                    ).strip()
                    
                    # Parse effective date
                    effective_date = None
                    date_str = (
                        row.get("EFFECTIVE_DATE") or
                        row.get("EffectiveDate") or
                        row.get("effective_date") or
                        ""
                    ).strip()
                    if date_str:
                        effective_date = self._parse_date(date_str)
                    
                    # Build content from available fields
                    content_parts = [f"LCD ID: {lcd_id}", f"Title: {title}"]
                    
                    if contractor:
                        content_parts.append(f"Contractor: {contractor}")
                    
                    # Add coverage indications if available
                    coverage = (
                        row.get("COVERAGE_INDICATIONS") or
                        row.get("CoverageIndications") or
                        row.get("coverage_indications") or
                        ""
                    ).strip()
                    if coverage:
                        content_parts.append(f"Coverage Indications:\n{coverage}")
                    
                    # Add limitations if available
                    limitations = (
                        row.get("LIMITATIONS") or
                        row.get("Limitations") or
                        row.get("limitations") or
                        ""
                    ).strip()
                    if limitations:
                        content_parts.append(f"Limitations:\n{limitations}")
                    
                    # Add CPT codes if available
                    cpt_codes = (
                        row.get("CPT_CODES") or
                        row.get("CptCodes") or
                        row.get("cpt_codes") or
                        ""
                    ).strip()
                    if cpt_codes:
                        content_parts.append(f"CPT Codes: {cpt_codes}")
                    
                    # Add ICD codes if available
                    icd_codes = (
                        row.get("ICD_CODES") or
                        row.get("IcdCodes") or
                        row.get("icd_codes") or
                        ""
                    ).strip()
                    if icd_codes:
                        content_parts.append(f"ICD Codes: {icd_codes}")
                    
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
                    logger.warning(f"Error parsing LCD row: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error parsing LCD CSV: {e}")
        
        return documents

    def _parse_ncd_csv(self, csv_content: str, filename: str = "") -> list[IngestedDocument]:
        """Parse NCD CSV content into documents."""
        documents = []
        
        # Skip non-NCD files based on filename
        filename_lower = filename.lower()
        
        # Only process the main ncd_trkg.csv file
        if filename and filename_lower != 'ncd_trkg.csv':
            logger.debug(f"Skipping non-main NCD file: {filename}")
            return documents
        
        try:
            reader = csv.DictReader(io.StringIO(csv_content))
            row_count = 0
            
            for row in reader:
                try:
                    # Get NCD ID - use NCD_mnl_sect as the display ID (e.g., "310.1")
                    ncd_id = (
                        row.get("NCD_mnl_sect") or 
                        row.get("NCD_id") or 
                        row.get("ncd_id") or
                        ""
                    ).strip()
                    
                    if not ncd_id:
                        continue
                    
                    # Get title
                    title = (
                        row.get("NCD_mnl_sect_title") or 
                        row.get("title") or 
                        row.get("Title") or
                        f"NCD {ncd_id}"
                    ).strip()
                    
                    # Parse effective date
                    effective_date = None
                    date_str = (
                        row.get("NCD_efctv_dt") or
                        row.get("EFFECTIVE_DATE") or
                        ""
                    ).strip()
                    if date_str:
                        effective_date = self._parse_date(date_str)
                    
                    # Build content from available fields
                    content_parts = [f"NCD ID: {ncd_id}", f"Title: {title}"]
                    
                    # Add item/service description
                    item_desc = (
                        row.get("itm_srvc_desc") or
                        ""
                    ).strip()
                    if item_desc:
                        item_desc = self._clean_html(item_desc)
                        content_parts.append(f"Item/Service Description:\n{item_desc}")
                    
                    # Add indications and limitations (main coverage content)
                    indications = (
                        row.get("indctn_lmtn") or
                        row.get("COVERAGE_INDICATIONS") or
                        ""
                    ).strip()
                    if indications:
                        indications = self._clean_html(indications)
                        content_parts.append(f"Coverage Indications and Limitations:\n{indications}")
                    
                    # Add cross-reference text
                    xref = (
                        row.get("xref_txt") or
                        ""
                    ).strip()
                    if xref:
                        xref = self._clean_html(xref)
                        content_parts.append(f"Cross References:\n{xref}")
                    
                    # Add other text
                    other = (
                        row.get("othr_txt") or
                        ""
                    ).strip()
                    if other:
                        other = self._clean_html(other)
                        content_parts.append(f"Additional Information:\n{other}")
                    
                    content = "\n\n".join(content_parts)
                    
                    # Build source URL
                    source_url = f"https://www.cms.gov/medicare-coverage-database/view/ncd.aspx?NCDId={row.get('NCD_id', ncd_id)}"
                    
                    metadata = DocumentMetadata(
                        document_id=ncd_id,
                        document_type=DocumentType.NCD,
                        title=title,
                        source_url=source_url,
                        effective_date=effective_date,
                        last_updated=datetime.utcnow(),
                    )
                    
                    chunks = self._create_chunks(ncd_id, content)
                    
                    documents.append(IngestedDocument(
                        metadata=metadata,
                        content=content,
                        chunks=chunks,
                    ))
                    row_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error parsing NCD row: {e}")
                    continue
            
            logger.info(f"Parsed {row_count} NCDs from {filename or 'csv content'}")
                    
        except Exception as e:
            logger.error(f"Error parsing NCD CSV: {e}")
        
        return documents

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from various formats."""
        date_formats = [
            "%m/%d/%Y",
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d-%b-%Y",
        ]
        
        date_str = date_str.strip()
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue
        
        return None

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
                    metadata={"source": "cms_downloads"},
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
                metadata={"source": "cms_downloads"},
            ))
        
        return chunks

    async def load_from_local_file(self, file_path: str) -> list[IngestedDocument]:
        """Load and parse a local ZIP file.
        
        Useful for testing or when downloads are pre-cached.
        
        Args:
            file_path: Path to the local ZIP file.
            
        Returns:
            List of ingested documents.
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"File not found: {file_path}")
            return []
        
        try:
            with open(path, "rb") as f:
                content = f.read()
            
            # Determine type from filename
            if "lcd" in path.name.lower():
                return self._parse_lcd_zip(content)
            elif "ncd" in path.name.lower():
                return self._parse_ncd_zip(content)
            else:
                logger.warning(f"Unknown file type: {path.name}")
                return []
                
        except Exception as e:
            logger.error(f"Error loading local file: {e}")
            return []
