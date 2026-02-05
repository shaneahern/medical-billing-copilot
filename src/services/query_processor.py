"""Query Processor service for Medical Billing Copilot.

Implements query classification, conversation context management,
and routing to the KnowledgeService for data retrieval.

Requirements: 1.1, 1.4
"""

import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from src.db.models import MessageRecord, Session
from src.schemas.common import Citation, DataSource, Message, QueryType
from src.schemas.knowledge import (
    CoverageLookupParams,
    DenialContext,
    LCDQueryParams,
    PriorAuthParams,
)
from src.schemas.query import QueryRequest, QueryResponse
from src.services.knowledge import KnowledgeService


class QueryProcessor:
    """Service for processing natural language queries.
    
    Handles query classification, conversation context management,
    and routing to the appropriate KnowledgeService methods.
    
    Requirements: 1.1, 1.4
    """

    # Patterns for query classification
    _COVERAGE_PATTERNS = [
        r"\bcoverage\b",
        r"\bcovered\b",
        r"\bcover\b",
        r"\bcpt\s*(?:code)?\s*\d{5}\b",
        r"\bicd\s*(?:code)?\s*[a-z]\d{2}",
        r"\breimburs",
        r"\bbillable\b",
    ]
    
    _LCD_PATTERNS = [
        r"\blcd\b",
        r"\blocal\s+coverage\s+determination\b",
        r"\bmac\s+region\b",
        r"\bnovitas\b",
        r"\bpalmetto\b",
        r"\bcgs\b",
        r"\bregional\s+coverage\b",
    ]
    
    _DENIAL_PATTERNS = [
        r"\bdenial\b",
        r"\bdenied\b",
        r"\bdeny\b",
        r"\bcarc\b",
        r"\breason\s+code\b",
        r"\brejection\b",
        r"\brejected\b",
        r"\bclaim\s+adjustment\b",
    ]
    
    _PRIOR_AUTH_PATTERNS = [
        r"\bprior\s+auth",
        r"\bpre\s*-?\s*auth",
        r"\bauthorization\b",
        r"\bpre\s*-?\s*approval\b",
        r"\bpa\s+required\b",
    ]

    def __init__(
        self,
        knowledge_service: KnowledgeService,
        db: DBSession,
    ) -> None:
        """Initialize QueryProcessor.
        
        Args:
            knowledge_service: KnowledgeService implementation for data retrieval
            db: SQLAlchemy database session
        """
        self.knowledge_service = knowledge_service
        self.db = db

    def _classify_query(self, query: str) -> QueryType:
        """Classify a query into one of the supported types.
        
        Args:
            query: Natural language query text
            
        Returns:
            QueryType classification
        """
        query_lower = query.lower()
        
        # Check patterns in order of specificity
        for pattern in self._DENIAL_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return QueryType.DENIAL_EXPLANATION
        
        for pattern in self._PRIOR_AUTH_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return QueryType.PRIOR_AUTH
        
        for pattern in self._LCD_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return QueryType.LCD_QUERY
        
        for pattern in self._COVERAGE_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                return QueryType.COVERAGE_LOOKUP
        
        return QueryType.GENERAL

    def _extract_cpt_code(self, text: str) -> Optional[str]:
        """Extract CPT code from text."""
        match = re.search(r"\b(\d{5})\b", text)
        return match.group(1) if match else None

    def _extract_icd_codes(self, text: str) -> list[str]:
        """Extract ICD codes from text."""
        # ICD-10 format: letter followed by 2+ digits, optionally with decimal
        matches = re.findall(r"\b([A-Z]\d{2}(?:\.\d{1,4})?)\b", text.upper())
        return matches

    def _extract_carc_code(self, text: str) -> Optional[str]:
        """Extract CARC code from text."""
        # CARC codes are 1-3 digit numbers
        match = re.search(r"\b(?:carc\s*)?(\d{1,3})\b", text.lower())
        return match.group(1) if match else None

    def _extract_payer(self, text: str) -> Optional[str]:
        """Extract payer name from text."""
        payers = [
            "medicare",
            "medicaid", 
            "aetna",
            "unitedhealth",
            "united healthcare",
            "cigna",
            "humana",
            "blue cross",
            "bcbs",
            "anthem",
        ]
        text_lower = text.lower()
        for payer in payers:
            if payer in text_lower:
                # Normalize payer names
                if payer in ["unitedhealth", "united healthcare"]:
                    return "UnitedHealthcare"
                if payer in ["blue cross", "bcbs"]:
                    return "Blue Cross Blue Shield"
                return payer.title()
        return None

    def _extract_mac_region(self, text: str) -> Optional[str]:
        """Extract MAC region from text."""
        # Check for specific MAC names
        mac_names = {
            "novitas": "Novitas",
            "palmetto": "Palmetto",
            "cgs": "CGS",
            "ngsmedicare": "NGS",
            "first coast": "First Coast",
            "noridian": "Noridian",
            "wisconsin physicians": "WPS",
        }
        text_lower = text.lower()
        for key, value in mac_names.items():
            if key in text_lower:
                return value
        
        # Check for MAC region codes
        match = re.search(r"\bmac\s*([a-z]|\d{1,2})\b", text_lower)
        if match:
            return match.group(1).upper()
        
        return None

    async def _get_conversation_context(
        self, session_id: str, limit: int = 5
    ) -> list[Message]:
        """Get recent conversation history for context.
        
        Args:
            session_id: Session identifier
            limit: Maximum number of messages to retrieve
            
        Returns:
            List of recent messages
        """
        messages = (
            self.db.query(MessageRecord)
            .filter(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.created_at.desc())
            .limit(limit)
            .all()
        )
        
        result = []
        for msg in reversed(messages):
            citations = None
            if msg.citations_json:
                try:
                    citations_data = json.loads(msg.citations_json)
                    citations = [Citation(**c) for c in citations_data]
                except (json.JSONDecodeError, TypeError):
                    pass
            
            result.append(
                Message(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    citations=citations,
                    timestamp=msg.created_at.replace(tzinfo=timezone.utc)
                    if msg.created_at.tzinfo is None
                    else msg.created_at,
                )
            )
        
        return result

    def _build_context_from_history(
        self, history: list[Message], current_query: str
    ) -> dict:
        """Build context dictionary from conversation history.
        
        Extracts relevant information from previous messages to
        provide context for follow-up queries.
        
        Args:
            history: Previous conversation messages
            current_query: Current query text
            
        Returns:
            Context dictionary with extracted information
        """
        context = {
            "previous_cpt_code": None,
            "previous_payer": None,
            "previous_mac_region": None,
            "previous_query_type": None,
        }
        
        # Look through history for context
        for msg in reversed(history):
            if msg.role == "user":
                if not context["previous_cpt_code"]:
                    context["previous_cpt_code"] = self._extract_cpt_code(msg.content)
                if not context["previous_payer"]:
                    context["previous_payer"] = self._extract_payer(msg.content)
                if not context["previous_mac_region"]:
                    context["previous_mac_region"] = self._extract_mac_region(msg.content)
        
        return context

    async def _handle_coverage_query(
        self, query: str, context: dict
    ) -> tuple[str, list[Citation], float]:
        """Handle a coverage lookup query."""
        cpt_code = self._extract_cpt_code(query)
        icd_codes = self._extract_icd_codes(query)
        payer = self._extract_payer(query) or context.get("previous_payer")
        mac_region = self._extract_mac_region(query) or context.get("previous_mac_region")
        
        # Only use previous CPT code if this looks like a follow-up question
        is_followup = any(phrase in query.lower() for phrase in [
            "what about", "how about", "is it", "same for", "and for",
            "that code", "this code", "the same", "also covered"
        ])
        if not cpt_code and is_followup:
            cpt_code = context.get("previous_cpt_code")
        
        # If no CPT code, try free-form text search on the policy database
        if not cpt_code:
            # Check if the knowledge service supports text search
            if hasattr(self.knowledge_service, 'search_policies'):
                search_results = await self.knowledge_service.search_policies(
                    query=query,
                    payer=payer,
                    mac_region=mac_region,
                    max_results=5,
                )
                
                if search_results:
                    # Build response from search results
                    response = "I found the following relevant policies:\n\n"
                    citations = []
                    
                    for i, result in enumerate(search_results[:3], 1):
                        response += f"**{i}. {result['title']}**\n"
                        response += f"   Type: {result['document_type']}"
                        if result.get('payer'):
                            response += f" | Payer: {result['payer']}"
                        if result.get('mac_region'):
                            response += f" | MAC: {result['mac_region']}"
                        response += "\n"
                        if result.get('snippet'):
                            snippet = result['snippet'][:200] + "..." if len(result.get('snippet', '')) > 200 else result.get('snippet', '')
                            response += f"   {snippet}\n"
                        response += "\n"
                        
                        citations.append(
                            Citation(
                                source_type=result['document_type'],
                                document_id=result['document_id'],
                                document_title=result['title'],
                                source_url=result.get('source_url'),
                            )
                        )
                    
                    response += "\nFor specific coverage details, please provide a CPT code (e.g., 'Is CPT 27447 covered?')."
                    return response, citations, 0.7
            
            return (
                "I need a CPT code to look up coverage. Please provide a 5-digit CPT code.",
                [],
                0.5,
            )
        
        params = CoverageLookupParams(
            cpt_code=cpt_code,
            icd_codes=icd_codes if icd_codes else None,
            payer=payer,
            mac_region=mac_region,
        )
        
        result = await self.knowledge_service.lookup_coverage(params)
        
        # Build response text
        payer_note = f" for {result.payer}" if result.payer else ""
        if result.is_covered:
            response = f"CPT code {result.cpt_code} ({result.cpt_description}) is covered{payer_note}."
            if result.conditions:
                response += "\n\nConditions for coverage:"
                for cond in result.conditions:
                    response += f"\n- {cond.description}"
            if result.restrictions:
                response += "\n\nRestrictions:"
                for restriction in result.restrictions:
                    response += f"\n- {restriction}"
        else:
            response = f"CPT code {result.cpt_code} is not covered{payer_note}."
            if result.restrictions:
                response += f"\n\nReason: {result.restrictions[0]}"
            if result.alternative_codes:
                response += "\n\nAlternative codes to consider:"
                for alt in result.alternative_codes:
                    response += f"\n- {alt.cpt_code}: {alt.description} ({alt.reason})"
        
        if not payer:
            response += "\n\n(Note: Defaulting to Medicare coverage. Specify a payer for payer-specific information.)"
        
        return response, result.sources, result.confidence

    async def _handle_lcd_query(
        self, query: str, context: dict
    ) -> tuple[str, list[Citation], float]:
        """Handle an LCD query."""
        mac_region = self._extract_mac_region(query) or context.get("previous_mac_region")
        cpt_code = self._extract_cpt_code(query) or context.get("previous_cpt_code")
        
        if not mac_region:
            return (
                "I need a MAC region to look up LCD information. Please specify a MAC region "
                "(e.g., Novitas, Palmetto, CGS) or I can show you national (NCD) coverage instead.",
                [],
                0.5,
            )
        
        params = LCDQueryParams(
            mac_region=mac_region,
            cpt_code=cpt_code,
        )
        
        try:
            result = await self.knowledge_service.query_lcd(params)
        except LookupError as e:
            return str(e), [], 0.3
        
        # Build response text
        response = f"**{result.title}** (LCD ID: {result.lcd_id})\n\n"
        response += f"MAC Region: {result.mac_name} ({result.mac_region})\n"
        response += f"Effective Date: {result.effective_date.strftime('%Y-%m-%d')}\n"
        
        if result.revision_history:
            response += "\n**Revision History:**"
            for rev in result.revision_history[:3]:  # Show last 3 revisions
                response += f"\n- v{rev.version} ({rev.effective_date.strftime('%Y-%m-%d')}): {rev.summary}"
        
        if result.covered_cpt_codes:
            response += f"\n\n**Covered CPT Codes:** {', '.join(result.covered_cpt_codes[:10])}"
            if len(result.covered_cpt_codes) > 10:
                response += f" (and {len(result.covered_cpt_codes) - 10} more)"
        
        if result.limitations:
            response += "\n\n**Limitations:**"
            for limit in result.limitations:
                response += f"\n- {limit}"
        
        if result.documentation_requirements:
            response += "\n\n**Documentation Requirements:**"
            for req in result.documentation_requirements:
                response += f"\n- {req}"
        
        response += f"\n\n[Source: {result.source_url}]"
        
        citations = [
            Citation(
                source_type="LCD",
                document_id=result.lcd_id,
                document_title=result.title,
                source_url=result.source_url,
                effective_date=result.effective_date,
            )
        ]
        
        return response, citations, 0.95

    async def _handle_denial_query(
        self, query: str, context: dict
    ) -> tuple[str, list[Citation], float]:
        """Handle a denial code explanation query."""
        carc_code = self._extract_carc_code(query)
        
        if not carc_code:
            return (
                "I need a CARC (Claim Adjustment Reason Code) to explain. "
                "Please provide a denial code number (e.g., 16, 29, 96).",
                [],
                0.5,
            )
        
        payer = self._extract_payer(query) or context.get("previous_payer")
        cpt_code = self._extract_cpt_code(query) or context.get("previous_cpt_code")
        
        denial_context = DenialContext(
            payer=payer,
            cpt_code=cpt_code,
        )
        
        try:
            result = await self.knowledge_service.explain_denial_code(
                carc_code, denial_context
            )
        except LookupError as e:
            return str(e), [], 0.3
        
        # Build response text
        response = f"**CARC {result.carc_code}: {result.short_description}**\n\n"
        response += f"Category: {result.category.value}\n\n"
        response += f"**Explanation:**\n{result.detailed_explanation}\n"
        
        if result.common_causes:
            response += "\n**Common Causes:**"
            for cause in result.common_causes:
                response += f"\n- {cause}"
        
        if result.recommended_actions:
            response += "\n\n**Recommended Actions:**"
            for action in sorted(result.recommended_actions, key=lambda x: x.priority):
                response += f"\n{action.priority}. {action.action}"
                if action.details:
                    response += f" - {action.details}"
        
        if result.related_codes:
            response += f"\n\n**Related Codes:** {', '.join(result.related_codes)}"
        
        citations = [
            Citation(
                source_type="CARC",
                document_id=f"CARC-{result.carc_code}",
                document_title=f"CARC {result.carc_code} - {result.short_description}",
            )
        ]
        
        return response, citations, 0.95

    async def _handle_prior_auth_query(
        self, query: str, context: dict
    ) -> tuple[str, list[Citation], float]:
        """Handle a prior authorization query."""
        cpt_code = self._extract_cpt_code(query) or context.get("previous_cpt_code")
        payer = self._extract_payer(query) or context.get("previous_payer")
        
        if not cpt_code:
            return (
                "I need a CPT code to check prior authorization requirements. "
                "Please provide a 5-digit CPT code.",
                [],
                0.5,
            )
        
        if not payer:
            return (
                f"I need a payer to check prior authorization requirements for CPT {cpt_code}. "
                "Please specify a payer (e.g., Medicare, Aetna, UnitedHealthcare).",
                [],
                0.5,
            )
        
        params = PriorAuthParams(
            cpt_code=cpt_code,
            payer=payer,
        )
        
        result = await self.knowledge_service.lookup_prior_auth(params)
        
        # Build response text
        auth_status = "required" if result.is_required else "not required"
        response = f"**Prior Authorization for CPT {result.cpt_code} with {result.payer}:** {auth_status.upper()}\n"
        
        if result.is_required:
            if result.submission_requirements:
                response += "\n**Submission Requirements:**"
                for req in result.submission_requirements:
                    response += f"\n- {req}"
            
            if result.typical_turnaround:
                response += f"\n\n**Typical Turnaround:** {result.typical_turnaround}"
            
            if result.plan_variations:
                response += "\n\n**Plan Variations:**"
                for var in result.plan_variations:
                    status = "Required" if var.is_required else "Not Required"
                    response += f"\n- {var.plan_type}: {status}"
                    if var.notes:
                        response += f" ({var.notes})"
            
            if result.urgent_exceptions:
                response += "\n\n**Urgent/Emergent Exceptions:**"
                for exc in result.urgent_exceptions:
                    response += f"\n- {exc}"
        
        if result.contact_info:
            response += f"\n\n**Contact:** {result.contact_info}"
        
        return response, result.sources, 0.9 if result.is_required else 0.7

    async def _handle_general_query(
        self, query: str, context: dict
    ) -> tuple[str, list[Citation], float]:
        """Handle a general query that doesn't match specific patterns."""
        response = (
            "I can help you with:\n\n"
            "- **Coverage lookups**: Ask about CPT code coverage (e.g., 'Is 99213 covered for Medicare?')\n"
            "- **LCD queries**: Look up Local Coverage Determinations by MAC region\n"
            "- **Denial explanations**: Explain CARC denial codes and recommended actions\n"
            "- **Prior authorization**: Check if prior auth is required for a procedure\n\n"
            "Please provide more details about what you'd like to know."
        )
        return response, [], 0.3

    async def process_query(self, request: QueryRequest) -> QueryResponse:
        """Process a natural language query and return a response.
        
        Args:
            request: Query request with session_id, user_id, query, and optional context
            
        Returns:
            QueryResponse with message, query type, confidence, and data source
        """
        # Get conversation history for context
        history = await self._get_conversation_context(request.session_id)
        
        # Build context from history and request
        context = self._build_context_from_history(history, request.query)
        if request.context:
            context.update(request.context)
        
        # Classify the query
        query_type = self._classify_query(request.query)
        
        # Route to appropriate handler
        if query_type == QueryType.COVERAGE_LOOKUP:
            content, citations, confidence = await self._handle_coverage_query(
                request.query, context
            )
        elif query_type == QueryType.LCD_QUERY:
            content, citations, confidence = await self._handle_lcd_query(
                request.query, context
            )
        elif query_type == QueryType.DENIAL_EXPLANATION:
            content, citations, confidence = await self._handle_denial_query(
                request.query, context
            )
        elif query_type == QueryType.PRIOR_AUTH:
            content, citations, confidence = await self._handle_prior_auth_query(
                request.query, context
            )
        else:
            content, citations, confidence = await self._handle_general_query(
                request.query, context
            )
        
        # Create response message
        message = Message(
            id=str(uuid.uuid4()),
            role="assistant",
            content=content,
            citations=citations if citations else None,
            timestamp=datetime.now(timezone.utc),
        )
        
        # Get data source info
        data_source_info = self.knowledge_service.get_data_source_info()
        
        return QueryResponse(
            message=message,
            query_type=query_type,
            confidence=confidence,
            data_source=data_source_info.type,
        )

    async def get_conversation_history(self, session_id: str) -> list[Message]:
        """Get full conversation history for a session.
        
        Args:
            session_id: Session identifier
            
        Returns:
            List of all messages in the session
        """
        messages = (
            self.db.query(MessageRecord)
            .filter(MessageRecord.session_id == session_id)
            .order_by(MessageRecord.created_at.asc())
            .all()
        )
        
        result = []
        for msg in messages:
            citations = None
            if msg.citations_json:
                try:
                    citations_data = json.loads(msg.citations_json)
                    citations = [Citation(**c) for c in citations_data]
                except (json.JSONDecodeError, TypeError):
                    pass
            
            result.append(
                Message(
                    id=msg.id,
                    role=msg.role,
                    content=msg.content,
                    citations=citations,
                    timestamp=msg.created_at.replace(tzinfo=timezone.utc)
                    if msg.created_at.tzinfo is None
                    else msg.created_at,
                )
            )
        
        return result

    async def create_session(self, user_id: str, title: Optional[str] = None) -> str:
        """Create a new conversation session.
        
        Args:
            user_id: User identifier
            title: Optional session title
            
        Returns:
            New session ID
        """
        session_id = str(uuid.uuid4())
        session = Session(
            id=session_id,
            user_id=user_id,
            title=title,
        )
        self.db.add(session)
        self.db.commit()
        return session_id

    async def save_message(
        self,
        session_id: str,
        role: str,
        content: str,
        citations: Optional[list[Citation]] = None,
    ) -> str:
        """Save a message to the conversation history.
        
        Args:
            session_id: Session identifier
            role: Message role (user or assistant)
            content: Message content
            citations: Optional list of citations
            
        Returns:
            Message ID
        """
        message_id = str(uuid.uuid4())
        citations_json = None
        if citations:
            citations_json = json.dumps([c.model_dump(mode="json") for c in citations])
        
        message = MessageRecord(
            id=message_id,
            session_id=session_id,
            role=role,
            content=content,
            citations_json=citations_json,
        )
        self.db.add(message)
        
        # Update session's last_activity and updated_at timestamps
        session = self.db.query(Session).filter(Session.id == session_id).first()
        if session:
            now = datetime.now(timezone.utc)
            session.last_activity = now
            session.updated_at = now
        
        self.db.commit()
        return message_id
