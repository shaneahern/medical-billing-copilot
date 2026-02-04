# Requirements Document

## Introduction

The Medical Billing Copilot is an AI-powered conversational Q&A interface designed for SMB medical billing departments. It provides instant answers to billing policy questions, denial code explanations, and coverage lookups without requiring EHR integration. The system addresses a market gap where enterprise solutions dominate at $50K+ contracts, leaving small billing teams underserved with no ChatGPT-like interface for billing policy questions.

This document is organized into two phases:
- **Phase 1 (MVP)**: Core application with stubbed/static data to validate UX and core workflows
- **Phase 2 (RAG Integration)**: Full RAG system with live policy data ingestion

### Technology Stack

- **Backend**: Python with FastAPI
- **RAG Framework**: LangChain or LlamaIndex
- **Vector Database**: ChromaDB, Pinecone, or similar
- **Web Frontend**: React, Vue, or simple HTML/JS
- **Web Scraping**: BeautifulSoup, Scrapy, or Playwright for dynamic content
- **Database**: PostgreSQL for user data and query logs

## Glossary

- **Copilot**: The AI-powered medical billing assistant system
- **User**: Medical billing staff, RCM managers, or billing department personnel
- **CPT_Code**: Current Procedural Terminology code identifying medical procedures
- **ICD_Code**: International Classification of Diseases code identifying diagnoses
- **LCD**: Local Coverage Determination - Medicare coverage policies specific to MAC regions
- **NCD**: National Coverage Determination - Medicare coverage policies applied nationally
- **MAC**: Medicare Administrative Contractor - regional Medicare administrators
- **CARC_Code**: Claim Adjustment Reason Code - standardized denial reason codes
- **Payer**: Insurance company or government program that pays claims
- **Prior_Authorization**: Pre-approval required from payer before service delivery
- **Query**: A natural language question submitted by the User to the Copilot
- **Policy_Database**: The indexed collection of LCDs, NCDs, and commercial payer policies
- **Coverage_Response**: The Copilot's answer to a coverage-related Query
- **Knowledge_Service**: Abstraction layer that provides policy data (stubbed in Phase 1, RAG-backed in Phase 2)
- **RAG_System**: Retrieval-Augmented Generation system that retrieves relevant documents before generating responses
- **Vector_Store**: Database storing document embeddings for semantic similarity search
- **Embedding**: Numerical vector representation of text for semantic search
- **Ingestion_Pipeline**: Automated system for processing and indexing policy documents
- **LLM_Integration**: Interface layer connecting the Copilot to large language models
- **Document_Chunk**: A semantic unit of text extracted from a policy document for indexing

---

## Phase 1: MVP Core Application

### Requirement 1: Conversational Q&A Interface

**User Story:** As a medical billing staff member, I want to ask billing questions in natural language, so that I can get instant answers during patient calls without searching through policy documents.

#### Acceptance Criteria

1. WHEN a User submits a Query in natural language, THE Copilot SHALL interpret the intent and return a relevant Coverage_Response within 3 seconds
2. WHEN a Query is ambiguous or incomplete, THE Copilot SHALL ask clarifying questions to refine the search
3. WHEN the Copilot returns a Coverage_Response, THE Copilot SHALL cite the source policy document (LCD, NCD, or commercial policy)
4. WHEN a User asks a follow-up question in the same session, THE Copilot SHALL maintain conversation context to provide relevant answers
5. IF the Copilot cannot find relevant policy information, THEN THE Copilot SHALL clearly indicate no matching policy was found and suggest alternative search terms

### Requirement 2: CPT Code Coverage Lookup

**User Story:** As a billing staff member, I want to check if a specific CPT code is covered for a diagnosis, so that I can verify coverage before or during patient encounters.

#### Acceptance Criteria

1. WHEN a User queries coverage for a CPT_Code and ICD_Code combination, THE Copilot SHALL return the coverage determination with applicable conditions
2. WHEN a CPT_Code has coverage restrictions, THE Copilot SHALL list all required conditions (diagnosis codes, frequency limits, documentation requirements)
3. WHEN a User specifies a Payer, THE Copilot SHALL return payer-specific coverage information
4. WHEN no Payer is specified, THE Copilot SHALL default to Medicare coverage and indicate this assumption
5. IF a CPT_Code is not covered for the specified ICD_Code, THEN THE Copilot SHALL explain why and suggest alternative covered codes if available

### Requirement 3: LCD Query by MAC Region

**User Story:** As an RCM manager, I want to look up Local Coverage Determinations by MAC region, so that I can understand regional Medicare coverage variations.

#### Acceptance Criteria

1. WHEN a User queries an LCD by MAC region, THE Copilot SHALL return the applicable LCD with effective dates
2. WHEN multiple LCDs apply to a procedure in a region, THE Copilot SHALL list all applicable LCDs with their scope
3. WHEN an LCD has been revised, THE Copilot SHALL indicate the revision history and current effective version
4. WHEN a User queries without specifying a MAC region, THE Copilot SHALL prompt for region selection or show national (NCD) coverage
5. THE Copilot SHALL display LCD article identifiers and links to source documents

### Requirement 4: Denial Code Explanation

**User Story:** As a billing staff member, I want to understand denial codes and get recommended fixes, so that I can resolve claim denials efficiently.

#### Acceptance Criteria

1. WHEN a User enters a CARC_Code, THE Copilot SHALL return a human-readable explanation of the denial reason
2. WHEN explaining a CARC_Code, THE Copilot SHALL provide recommended corrective actions specific to that code
3. WHEN a CARC_Code has common root causes, THE Copilot SHALL list the most frequent causes based on industry patterns
4. WHEN a User provides additional context (payer, procedure), THE Copilot SHALL tailor the explanation and recommendations
5. THE Copilot SHALL categorize denial explanations by type (eligibility, authorization, coding, documentation)

### Requirement 5: Prior Authorization Lookup

**User Story:** As a billing staff member, I want to check prior authorization requirements by payer and procedure, so that I can ensure proper authorization before service delivery.

#### Acceptance Criteria

1. WHEN a User queries prior authorization requirements for a CPT_Code and Payer, THE Copilot SHALL return whether Prior_Authorization is required
2. WHEN Prior_Authorization is required, THE Copilot SHALL provide submission requirements and typical turnaround times
3. WHEN Prior_Authorization requirements vary by plan type, THE Copilot SHALL indicate plan-specific variations
4. IF Prior_Authorization information is unavailable for a Payer, THEN THE Copilot SHALL indicate this and recommend contacting the payer directly
5. WHEN a procedure has urgent/emergent exceptions, THE Copilot SHALL note the exception criteria

### Requirement 6: Knowledge Service Abstraction

**User Story:** As a developer, I want a knowledge service abstraction layer, so that the application can work with stubbed data initially and swap to RAG-backed data without changing the UI.

#### Acceptance Criteria

1. THE Knowledge_Service SHALL expose a unified interface for all policy lookups (coverage, LCD, denial codes, prior auth)
2. THE Knowledge_Service SHALL support a stubbed implementation with static JSON data for MVP testing
3. THE Knowledge_Service SHALL support swapping implementations without changes to consuming components
4. WHEN the Knowledge_Service returns data, THE Knowledge_Service SHALL include metadata indicating data source and freshness
5. THE Knowledge_Service SHALL define TypeScript interfaces for all data models (CoverageResult, LCDResult, DenialExplanation, PriorAuthResult)

### Requirement 7: User Authentication and Session Management

**User Story:** As a billing department administrator, I want secure user authentication, so that our billing queries remain confidential and usage can be tracked.

#### Acceptance Criteria

1. WHEN a User accesses the Copilot, THE Copilot SHALL require authentication via email and password
2. THE Copilot SHALL support session persistence so Users remain logged in across browser sessions
3. WHEN a session is inactive for 30 minutes, THE Copilot SHALL require re-authentication
4. THE Copilot SHALL log all Queries for audit purposes with timestamps and user identifiers
5. IF authentication fails three consecutive times, THEN THE Copilot SHALL temporarily lock the account and notify the administrator

### Requirement 8: Web Application Interface

**User Story:** As a billing staff member, I want to access the Copilot through a web browser, so that I can use it on any computer without installing software.

#### Acceptance Criteria

1. THE Copilot SHALL be accessible via modern web browsers (Chrome, Firefox, Safari, Edge)
2. THE Copilot SHALL provide a responsive interface usable on desktop and tablet devices
3. WHEN a User submits a Query, THE Copilot SHALL display a loading indicator until the response is ready
4. THE Copilot SHALL maintain conversation history within a session for reference
5. THE Copilot SHALL allow Users to start a new conversation while preserving previous session history

### Requirement 9: Stubbed Policy Data

**User Story:** As a developer, I want realistic stubbed policy data, so that I can test the full application flow before RAG integration.

#### Acceptance Criteria

1. THE Stubbed_Data SHALL include sample Medicare LCDs for at least 3 MAC regions
2. THE Stubbed_Data SHALL include sample NCDs for common procedures
3. THE Stubbed_Data SHALL include CARC code definitions with explanations and recommended actions
4. THE Stubbed_Data SHALL include prior authorization requirements for at least 3 major payers
5. THE Stubbed_Data SHALL include CPT-to-ICD coverage mappings for common procedure/diagnosis combinations
6. WHEN stubbed data is used, THE Copilot SHALL display a visual indicator that data is from test/demo source

---

## Phase 2: RAG System Integration

### Requirement 10: RAG-Based Knowledge Retrieval System

**User Story:** As a system architect, I want a Retrieval-Augmented Generation system, so that the Copilot can provide accurate, source-grounded answers from policy documents.

#### Acceptance Criteria

1. WHEN a User submits a Query, THE RAG_System SHALL convert the query into vector embeddings for semantic search
2. THE RAG_System SHALL retrieve the top-k most relevant document chunks from the Vector_Store before generating a response
3. WHEN generating a Coverage_Response, THE RAG_System SHALL ground the response in retrieved document content
4. THE RAG_System SHALL include relevance scores for retrieved documents to filter low-confidence matches
5. IF retrieved documents have relevance scores below the confidence threshold, THEN THE RAG_System SHALL indicate uncertainty in the response
6. THE RAG_System SHALL support hybrid search combining semantic similarity and keyword matching

### Requirement 11: Data Ingestion Pipeline

**User Story:** As a data engineer, I want an automated data ingestion pipeline, so that policy documents are continuously indexed and kept current.

#### Acceptance Criteria

1. THE Ingestion_Pipeline SHALL support ingestion from CMS.gov for Medicare LCDs and NCDs
2. THE Ingestion_Pipeline SHALL support ingestion of commercial payer policy PDFs and web pages
3. WHEN a document is ingested, THE Ingestion_Pipeline SHALL extract text, chunk it into semantic units, and generate embeddings
4. THE Ingestion_Pipeline SHALL maintain document metadata (source, effective date, payer, region, document type)
5. WHEN a source document is updated, THE Ingestion_Pipeline SHALL detect changes and re-index affected chunks
6. THE Ingestion_Pipeline SHALL log all ingestion activities with success/failure status for monitoring
7. THE Ingestion_Pipeline SHALL support scheduled batch ingestion and on-demand manual triggers

### Requirement 12: Vector Store and Document Management

**User Story:** As a system architect, I want a scalable vector store, so that document embeddings can be efficiently searched at query time.

#### Acceptance Criteria

1. THE Vector_Store SHALL store document embeddings with associated metadata and source text
2. THE Vector_Store SHALL support approximate nearest neighbor search with sub-second query latency
3. WHEN documents are updated, THE Vector_Store SHALL support incremental updates without full re-indexing
4. THE Vector_Store SHALL support filtering by metadata (payer, region, document type, effective date)
5. THE Vector_Store SHALL maintain version history for document chunks to support rollback

### Requirement 13: LLM Integration and Response Generation

**User Story:** As a system architect, I want integration with a large language model, so that the Copilot can generate natural language responses from retrieved context.

#### Acceptance Criteria

1. THE LLM_Integration SHALL send retrieved document context and user query to the language model
2. THE LLM_Integration SHALL use prompt templates optimized for medical billing Q&A
3. WHEN generating responses, THE LLM_Integration SHALL instruct the model to cite specific sources
4. THE LLM_Integration SHALL enforce response length limits appropriate for conversational interface
5. IF the LLM generates content not grounded in retrieved documents, THEN THE LLM_Integration SHALL flag the response as potentially unverified
6. THE LLM_Integration SHALL support configurable model selection (GPT-4, Claude, etc.) for flexibility

### Requirement 14: Payer Policy Database

**User Story:** As an RCM manager, I want access to a comprehensive payer policy database, so that I can reference accurate coverage information across multiple payers.

#### Acceptance Criteria

1. THE Policy_Database SHALL contain current Medicare LCDs and NCDs
2. THE Policy_Database SHALL contain major commercial payer policies (top 10 national payers by market share)
3. WHEN policy documents are updated by payers, THE Policy_Database SHALL reflect updates within 7 days
4. THE Copilot SHALL display the last-updated date for any policy information returned
5. WHEN a User queries a payer not in the database, THE Copilot SHALL indicate the payer is not currently supported
