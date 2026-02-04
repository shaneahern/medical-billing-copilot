"""Pydantic schemas for Medical Billing Copilot API."""

from src.schemas.auth import (
    AuthResult,
    LoginRequest,
    RefreshRequest,
    TokenPayload,
    UserProfile,
)
from src.schemas.common import (
    Citation,
    ConditionType,
    DataSource,
    DenialCategory,
    Message,
    QueryType,
    UserRole,
)
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
from src.schemas.query import (
    QueryRequest,
    QueryResponse,
)
from src.schemas.session import (
    SessionCreate,
    SessionResponse,
    SessionWithMessages,
)

__all__ = [
    # Common
    "Citation",
    "ConditionType",
    "DataSource",
    "DenialCategory",
    "Message",
    "QueryType",
    "UserRole",
    # Auth
    "AuthResult",
    "LoginRequest",
    "RefreshRequest",
    "TokenPayload",
    "UserProfile",
    # Knowledge
    "AlternativeCode",
    "CoverageLookupParams",
    "CoverageCondition",
    "CoverageResult",
    "DataSourceInfo",
    "DenialContext",
    "DenialExplanation",
    "LCDQueryParams",
    "LCDResult",
    "LCDRevision",
    "PlanVariation",
    "PriorAuthParams",
    "PriorAuthResult",
    "RecommendedAction",
    # Query
    "QueryRequest",
    "QueryResponse",
    # Session
    "SessionCreate",
    "SessionResponse",
    "SessionWithMessages",
]
