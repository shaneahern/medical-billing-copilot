"""Query API endpoints for Medical Billing Copilot.

Implements coverage lookup, LCD query, denial code explanation,
prior auth lookup, and main query endpoints.

Requirements: 1.1, 1.2, 1.3, 1.5, 2.1-2.4, 3.1-3.5, 4.1-4.5, 5.1-5.5
"""

import time
import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from src.db.config import get_db
from src.db.models import QueryLog
from src.schemas.common import Citation, DataSource, Message, QueryType
from src.schemas.knowledge import (
    CoverageLookupParams,
    CoverageResult,
    DenialContext,
    DenialExplanation,
    LCDQueryParams,
    LCDResult,
    PriorAuthParams,
    PriorAuthResult,
)
from src.schemas.query import QueryRequest, QueryResponse
from src.services import (
    AuthService,
    InvalidTokenError,
    KnowledgeService,
    QueryProcessor,
    TokenExpiredError,
)
from src.services.knowledge_factory import get_knowledge_service as factory_get_knowledge_service

router = APIRouter(prefix="/api", tags=["query"])
security = HTTPBearer()


# Request/Response models for endpoints
class CoverageRequest(BaseModel):
    """Coverage lookup request body."""

    cpt_code: str = Field(
        ..., pattern=r"^[0-9]{5}$", description="CPT code (5 digits)"
    )
    icd_codes: Optional[list[str]] = Field(None, description="ICD codes")
    payer: Optional[str] = Field(None, description="Payer name (defaults to Medicare)")


class LCDQueryRequest(BaseModel):
    """LCD query parameters."""

    mac_region: Optional[str] = Field(None, description="MAC region")
    cpt_code: Optional[str] = Field(
        None, pattern=r"^[0-9]{5}$", description="CPT code"
    )
    lcd_id: Optional[str] = Field(None, description="LCD identifier")


class LCDPromptResponse(BaseModel):
    """Response when MAC region is not specified."""

    message: str = Field(..., description="Prompt message")
    available_regions: list[str] = Field(..., description="Available MAC regions")


class PriorAuthRequest(BaseModel):
    """Prior auth lookup parameters."""

    cpt_code: str = Field(
        ..., pattern=r"^[0-9]{5}$", description="CPT code (5 digits)"
    )
    payer: str = Field(..., description="Payer name")
    plan_type: Optional[str] = Field(None, description="Plan type")


class NaturalLanguageQueryRequest(BaseModel):
    """Natural language query request."""

    query: str = Field(
        ..., min_length=1, max_length=10000, description="Natural language query"
    )
    session_id: Optional[str] = Field(None, description="Session ID for context")


# Dependency functions
def get_knowledge_service() -> KnowledgeService:
    """Get the knowledge service instance based on configuration.
    
    Uses the knowledge service factory to return either StubbedKnowledgeService
    or RAGKnowledgeService based on settings.knowledge_service_type.
    
    Requirements: 6.3, 13.6
    """
    return factory_get_knowledge_service()


def get_query_processor(
    db: DBSession = Depends(get_db),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> QueryProcessor:
    """Get the query processor instance."""
    return QueryProcessor(knowledge_service=knowledge_service, db=db)


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(security)],
    db: DBSession = Depends(get_db),
) -> dict:
    """Validate JWT token and return current user info."""
    auth_service = AuthService(db)
    try:
        token_payload = auth_service.validate_token(credentials.credentials)
        return {
            "user_id": token_payload.user_id,
            "email": token_payload.email,
            "role": token_payload.role,
        }
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


def log_query(
    db: DBSession,
    session_id: str,
    user_id: str,
    query: str,
    query_type: QueryType,
    response_time_ms: int,
    data_source: DataSource,
) -> None:
    """Log a query for audit purposes."""
    query_log = QueryLog(
        id=str(uuid.uuid4()),
        session_id=session_id,
        user_id=user_id,
        query=query,
        query_type=query_type.value,
        response_time_ms=response_time_ms,
        data_source=data_source.value,
    )
    db.add(query_log)
    db.commit()


# Endpoints
@router.post("/coverage", response_model=CoverageResult)
async def lookup_coverage(
    request: CoverageRequest,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> CoverageResult:
    """Look up coverage for a CPT code.
    
    POST /api/coverage with CPT, ICD, payer parameters.
    Defaults to Medicare when payer not specified.
    Returns coverage result with citations.
    
    Requirements: 2.1, 2.2, 2.3, 2.4
    """
    start_time = time.time()
    
    params = CoverageLookupParams(
        cpt_code=request.cpt_code,
        icd_codes=request.icd_codes,
        payer=request.payer,  # Will default to Medicare in service
    )
    
    result = await knowledge_service.lookup_coverage(params)
    
    # Get data source from knowledge service
    data_source_info = knowledge_service.get_data_source_info()
    
    # Log the query for audit (Requirement 7.4)
    response_time_ms = int((time.time() - start_time) * 1000)
    # Use a placeholder session_id for direct API calls
    log_query(
        db=db,
        session_id="direct-api-call",
        user_id=current_user["user_id"],
        query=f"Coverage lookup: CPT={request.cpt_code}, ICD={request.icd_codes}, Payer={request.payer}",
        query_type=QueryType.COVERAGE_LOOKUP,
        response_time_ms=response_time_ms,
        data_source=data_source_info.type,
    )
    
    return result


@router.get("/lcd", response_model=LCDResult | LCDPromptResponse)
async def query_lcd(
    mac_region: Optional[str] = Query(None, description="MAC region"),
    cpt_code: Optional[str] = Query(None, pattern=r"^[0-9]{5}$", description="CPT code"),
    lcd_id: Optional[str] = Query(None, description="LCD identifier"),
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> LCDResult | LCDPromptResponse:
    """Query Local Coverage Determination by MAC region.
    
    GET /api/lcd with MAC region and CPT code parameters.
    Prompts for region if not specified.
    Returns LCD with revision history.
    
    Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
    """
    start_time = time.time()
    
    if not mac_region:
        # Prompt for region selection per Requirement 3.4
        return LCDPromptResponse(
            message="Please specify a MAC region to look up LCD information, "
            "or I can show you national (NCD) coverage instead.",
            available_regions=["Novitas", "Palmetto", "CGS"],
        )
    
    params = LCDQueryParams(
        mac_region=mac_region,
        cpt_code=cpt_code,
        lcd_id=lcd_id,
    )
    
    try:
        result = await knowledge_service.query_lcd(params)
        
        # Get data source from knowledge service
        data_source_info = knowledge_service.get_data_source_info()
        
        # Log the query for audit (Requirement 7.4)
        response_time_ms = int((time.time() - start_time) * 1000)
        log_query(
            db=db,
            session_id="direct-api-call",
            user_id=current_user["user_id"],
            query=f"LCD query: MAC={mac_region}, CPT={cpt_code}, LCD_ID={lcd_id}",
            query_type=QueryType.LCD_QUERY,
            response_time_ms=response_time_ms,
            data_source=data_source_info.type,
        )
        
        return result
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/denial-codes/{code}", response_model=DenialExplanation)
async def explain_denial_code(
    code: str,
    payer: Optional[str] = Query(None, description="Payer name for context"),
    cpt_code: Optional[str] = Query(None, description="Related CPT code"),
    claim_type: Optional[str] = Query(None, description="Claim type"),
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> DenialExplanation:
    """Explain a CARC denial code.
    
    GET /api/denial-codes/{code}
    Returns categorized explanation with recommended actions.
    
    Requirements: 4.1, 4.2, 4.3, 4.4, 4.5
    """
    start_time = time.time()
    
    context = DenialContext(
        payer=payer,
        cpt_code=cpt_code,
        claim_type=claim_type,
    )
    
    try:
        result = await knowledge_service.explain_denial_code(code, context)
        
        # Get data source from knowledge service
        data_source_info = knowledge_service.get_data_source_info()
        
        # Log the query for audit (Requirement 7.4)
        response_time_ms = int((time.time() - start_time) * 1000)
        log_query(
            db=db,
            session_id="direct-api-call",
            user_id=current_user["user_id"],
            query=f"Denial code explanation: CARC={code}, Payer={payer}, CPT={cpt_code}",
            query_type=QueryType.DENIAL_EXPLANATION,
            response_time_ms=response_time_ms,
            data_source=data_source_info.type,
        )
        
        return result
    except LookupError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get("/prior-auth", response_model=PriorAuthResult)
async def lookup_prior_auth(
    cpt_code: str = Query(..., pattern=r"^[0-9]{5}$", description="CPT code"),
    payer: str = Query(..., description="Payer name"),
    plan_type: Optional[str] = Query(None, description="Plan type"),
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> PriorAuthResult:
    """Look up prior authorization requirements.
    
    GET /api/prior-auth with CPT and payer parameters.
    Returns auth requirements with plan variations.
    
    Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
    """
    start_time = time.time()
    
    params = PriorAuthParams(
        cpt_code=cpt_code,
        payer=payer,
        plan_type=plan_type,
    )
    
    result = await knowledge_service.lookup_prior_auth(params)
    
    # Get data source from knowledge service
    data_source_info = knowledge_service.get_data_source_info()
    
    # Log the query for audit (Requirement 7.4)
    response_time_ms = int((time.time() - start_time) * 1000)
    log_query(
        db=db,
        session_id="direct-api-call",
        user_id=current_user["user_id"],
        query=f"Prior auth lookup: CPT={cpt_code}, Payer={payer}, Plan={plan_type}",
        query_type=QueryType.PRIOR_AUTH,
        response_time_ms=response_time_ms,
        data_source=data_source_info.type,
    )
    
    return result


@router.post("/query", response_model=QueryResponse)
async def submit_query(
    request: NaturalLanguageQueryRequest,
    current_user: dict = Depends(get_current_user),
    db: DBSession = Depends(get_db),
    query_processor: QueryProcessor = Depends(get_query_processor),
) -> QueryResponse:
    """Submit a natural language query.
    
    POST /api/query for natural language queries.
    Classifies query type and routes to appropriate handler.
    Returns response with citations within 3 seconds.
    
    Requirements: 1.1, 1.2, 1.3, 1.5
    """
    start_time = time.time()
    
    # Create or use existing session
    session_id = request.session_id
    if not session_id:
        session_id = await query_processor.create_session(
            user_id=current_user["user_id"]
        )
    
    # Save user message
    await query_processor.save_message(
        session_id=session_id,
        role="user",
        content=request.query,
    )
    
    # Process the query
    query_request = QueryRequest(
        session_id=session_id,
        user_id=current_user["user_id"],
        query=request.query,
    )
    
    response = await query_processor.process_query(query_request)
    
    # Save assistant response
    await query_processor.save_message(
        session_id=session_id,
        role="assistant",
        content=response.message.content,
        citations=response.message.citations,
    )
    
    # Calculate response time
    response_time_ms = int((time.time() - start_time) * 1000)
    
    # Log the query for audit
    log_query(
        db=db,
        session_id=session_id,
        user_id=current_user["user_id"],
        query=request.query,
        query_type=response.query_type,
        response_time_ms=response_time_ms,
        data_source=response.data_source,
    )
    
    return response



@router.get("/data-source")
async def get_data_source_info(
    current_user: dict = Depends(get_current_user),
    knowledge_service: KnowledgeService = Depends(get_knowledge_service),
) -> dict:
    """Get information about the current data source.
    
    Returns data source indicator for UI display.
    
    Requirements: 9.6, 13.6
    """
    from src.services.knowledge_factory import get_data_source_indicator
    
    return get_data_source_indicator()
