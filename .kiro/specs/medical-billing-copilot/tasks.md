# Implementation Plan: Medical Billing Copilot

## Overview

This implementation plan covers the Medical Billing Copilot - an AI-powered Q&A web application for SMB medical billing teams. The plan is organized into two phases:

- **Phase 1 (MVP)**: Core application with stubbed policy data
- **Phase 2**: RAG integration with live policy data ingestion

Tasks are ordered to enable incremental development with early validation of core functionality.

## Tasks

### Phase 1: MVP Core Application

- [ ] 1. Project setup and infrastructure
  - [x] 1.1 Initialize Python project with FastAPI
    - Create project structure with `src/`, `tests/`, `data/` directories
    - Set up `pyproject.toml` with dependencies (fastapi, uvicorn, pydantic, sqlalchemy, python-jose, passlib, hypothesis)
    - Configure pytest and hypothesis settings
    - _Requirements: 8.1_

  - [x] 1.2 Set up PostgreSQL database and SQLAlchemy models
    - Create database models for User, Session, MessageRecord, QueryLog
    - Set up Alembic for migrations
    - Create initial migration
    - _Requirements: 7.1, 7.4_

  - [x] 1.3 Create Pydantic schemas for API request/response models
    - Define all request/response models from design document
    - Create shared types (Citation, Message, QueryType, etc.)
    - _Requirements: 6.5_

- [ ] 2. Authentication service
  - [x] 2.1 Implement JWT-based authentication
    - Create AuthService with login, logout, refresh_token, validate_token methods
    - Implement password hashing with passlib
    - Configure JWT token generation and validation
    - _Requirements: 7.1, 7.2_

  - [x] 2.2 Implement account lockout mechanism
    - Track failed login attempts in User model
    - Lock account after 3 consecutive failures
    - Implement lockout duration and reset logic
    - _Requirements: 7.5_

  - [x] 2.3 Implement session timeout
    - Configure 30-minute inactivity timeout
    - Validate session freshness on each request
    - _Requirements: 7.3_

  - [ ]* 2.4 Write property tests for authentication
    - **Property 14: Authentication enforcement**
    - **Property 16: Account lockout enforcement**
    - **Validates: Requirements 7.1, 7.5**

- [x] 3. Knowledge Service abstraction layer
  - [x] 3.1 Define KnowledgeService abstract base class
    - Create abstract methods: lookup_coverage, query_lcd, explain_denial_code, lookup_prior_auth
    - Define get_data_source_info method
    - _Requirements: 6.1, 6.3_

  - [x] 3.2 Create stubbed policy data JSON files
    - Create sample Medicare LCDs for 3 MAC regions (Novitas, Palmetto, CGS)
    - Create sample NCDs for common procedures (99213, 99214, 99215)
    - Create CARC code definitions with explanations
    - Create prior auth requirements for Medicare, Aetna, UnitedHealthcare
    - Create CPT-to-ICD coverage mappings
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [x] 3.3 Implement StubbedKnowledgeService
    - Load JSON stub files on initialization
    - Implement all KnowledgeService methods using stub data
    - Include data source indicator in responses
    - _Requirements: 6.2, 6.4, 9.6_

  - [ ]* 3.4 Write property tests for Knowledge Service
    - **Property 12: Knowledge service interchangeability**
    - **Property 13: Data source metadata inclusion**
    - **Validates: Requirements 6.3, 6.4**

- [ ] 4. Checkpoint - Core services complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Query processor and API endpoints
  - [ ] 5.1 Implement QueryProcessor service
    - Create query classification logic (coverage, LCD, denial, prior auth, general)
    - Implement conversation context management
    - Wire to KnowledgeService for data retrieval
    - _Requirements: 1.1, 1.4_

  - [ ] 5.2 Implement coverage lookup endpoint
    - POST /api/coverage with CPT, ICD, payer parameters
    - Default to Medicare when payer not specified
    - Return coverage result with citations
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ] 5.3 Implement LCD query endpoint
    - GET /api/lcd with MAC region and CPT code parameters
    - Prompt for region if not specified
    - Return LCD with revision history
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ] 5.4 Implement denial code explanation endpoint
    - GET /api/denial-codes/{code}
    - Return categorized explanation with recommended actions
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ] 5.5 Implement prior auth lookup endpoint
    - GET /api/prior-auth with CPT and payer parameters
    - Return auth requirements with plan variations
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ] 5.6 Implement main query endpoint
    - POST /api/query for natural language queries
    - Classify query type and route to appropriate handler
    - Return response with citations within 3 seconds
    - _Requirements: 1.1, 1.2, 1.3, 1.5_

  - [ ]* 5.7 Write property tests for query processing
    - **Property 1: Response time compliance**
    - **Property 2: Source citation completeness**
    - **Property 5: Coverage lookup completeness**
    - **Property 6: Payer filtering correctness**
    - **Property 7: Non-covered code handling**
    - **Property 8: LCD query completeness**
    - **Property 10: CARC explanation completeness**
    - **Property 11: Prior auth response completeness**
    - **Validates: Requirements 1.1, 1.3, 2.1-2.5, 3.1-3.5, 4.1-4.5, 5.1-5.5**

- [ ] 6. Session management
  - [ ] 6.1 Implement session CRUD endpoints
    - POST /api/sessions - create new session
    - GET /api/sessions - list user sessions
    - GET /api/sessions/{id} - get session with messages
    - DELETE /api/sessions/{id} - delete session
    - _Requirements: 8.4, 8.5_

  - [ ] 6.2 Implement conversation history storage
    - Store messages in MessageRecord table
    - Maintain session context for follow-up queries
    - _Requirements: 1.4, 8.4_

  - [ ] 6.3 Implement query audit logging
    - Log all queries to QueryLog table
    - Include user ID, session ID, query type, response time
    - _Requirements: 7.4_

  - [ ]* 6.4 Write property tests for session management
    - **Property 3: Session context preservation**
    - **Property 17: Query audit logging**
    - **Property 18: Session history isolation**
    - **Validates: Requirements 1.4, 7.4, 8.4, 8.5**

- [ ] 7. Checkpoint - Backend complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. React frontend
  - [ ] 8.1 Initialize React project with TypeScript
    - Set up Vite with React and TypeScript
    - Configure TailwindCSS for styling
    - Set up API client with axios
    - _Requirements: 8.1_

  - [ ] 8.2 Implement authentication UI
    - Create login form component
    - Implement JWT token storage and refresh
    - Create protected route wrapper
    - _Requirements: 7.1, 7.2_

  - [ ] 8.3 Implement chat interface
    - Create ChatInterface component with message list
    - Create QueryInput component with submit handling
    - Create ResponseDisplay component with citation rendering
    - Implement loading indicator during queries
    - _Requirements: 8.2, 8.3_

  - [ ] 8.4 Implement session management UI
    - Create session list sidebar
    - Implement new session creation
    - Implement session switching and history display
    - _Requirements: 8.4, 8.5_

  - [ ] 8.5 Add stubbed data indicator
    - Display visual indicator when using stubbed data
    - Show data source info in responses
    - _Requirements: 9.6_

- [ ] 9. Checkpoint - Phase 1 MVP complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify end-to-end flow from UI to stubbed knowledge service

### Phase 2: RAG Integration

- [ ] 10. Vector store setup
  - [ ] 10.1 Set up ChromaDB for development
    - Configure ChromaDB with persistent storage
    - Create collection for policy documents
    - Implement embedding generation with OpenAI
    - _Requirements: 12.1, 12.2_

  - [ ] 10.2 Implement document chunking
    - Create semantic chunking for policy documents
    - Maintain metadata (source, payer, region, effective date)
    - _Requirements: 11.3, 11.4_

  - [ ] 10.3 Implement vector store operations
    - Add documents with embeddings
    - Query with similarity search
    - Support metadata filtering
    - _Requirements: 12.2, 12.4_

  - [ ]* 10.4 Write property tests for vector store
    - Test document storage and retrieval consistency
    - Test metadata filtering accuracy
    - **Validates: Requirements 12.1-12.5**

- [ ] 11. Data ingestion pipeline
  - [ ] 11.1 Implement CMS.gov scraper for LCDs/NCDs
    - Scrape Medicare LCD and NCD documents
    - Extract text content and metadata
    - Handle pagination and document links
    - _Requirements: 11.1_

  - [ ] 11.2 Implement commercial payer policy scraper
    - Support PDF extraction with PyPDF2
    - Support web page scraping with BeautifulSoup/Playwright
    - Extract policy text and metadata
    - _Requirements: 11.2_

  - [ ] 11.3 Implement ingestion orchestration
    - Create scheduled batch ingestion jobs
    - Support manual trigger for on-demand ingestion
    - Log ingestion activities with success/failure status
    - _Requirements: 11.5, 11.6, 11.7_

  - [ ]* 11.4 Write integration tests for ingestion pipeline
    - Test document extraction accuracy
    - Test change detection and re-indexing
    - **Validates: Requirements 11.1-11.7**

- [ ] 12. RAG Knowledge Service
  - [ ] 12.1 Implement RAGKnowledgeService
    - Initialize LangChain with vector store retriever
    - Configure retrieval parameters (top-k, similarity threshold)
    - Implement hybrid search (semantic + keyword)
    - _Requirements: 10.1, 10.2, 10.6_

  - [ ] 12.2 Implement LLM integration
    - Configure OpenAI/Anthropic client
    - Create prompt templates for medical billing Q&A
    - Implement response generation with source grounding
    - _Requirements: 13.1, 13.2, 13.3_

  - [ ] 12.3 Implement confidence scoring
    - Calculate relevance scores for retrieved documents
    - Flag low-confidence responses
    - Indicate uncertainty when below threshold
    - _Requirements: 10.4, 10.5, 13.5_

  - [ ] 12.4 Wire RAGKnowledgeService to application
    - Configure service selection (stubbed vs RAG)
    - Update data source indicator in responses
    - _Requirements: 6.3, 13.6_

  - [ ]* 12.5 Write property tests for RAG service
    - **Property 4: Not-found response handling**
    - **Property 9: MAC region requirement**
    - Test response grounding in retrieved documents
    - **Validates: Requirements 10.1-10.6, 13.1-13.6**

- [ ] 13. Payer policy database
  - [ ] 13.1 Ingest Medicare LCDs and NCDs
    - Run ingestion for all MAC regions
    - Verify coverage of common procedures
    - _Requirements: 14.1_

  - [ ] 13.2 Ingest commercial payer policies
    - Ingest policies for top 10 national payers
    - Verify policy freshness within 7 days
    - _Requirements: 14.2, 14.3_

  - [ ] 13.3 Implement policy freshness tracking
    - Display last-updated date in responses
    - Indicate unsupported payers
    - _Requirements: 14.4, 14.5_

- [ ] 14. Final checkpoint - Phase 2 complete
  - Ensure all tests pass, ask the user if questions arise.
  - Verify end-to-end RAG flow with live policy data

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties
- Phase 1 can be deployed independently for early user feedback
- Phase 2 builds on Phase 1 without requiring UI changes (thanks to Knowledge Service abstraction)
