export interface Citation {
  source_type: 'LCD' | 'NCD' | 'COMMERCIAL' | 'CARC';
  document_id: string;
  document_title: string;
  source_url?: string;
  effective_date?: string;
}

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  timestamp: string;
}

export interface Session {
  id: string;
  user_id: string;
  title?: string;
  created_at: string;
  updated_at: string;
  last_activity?: string;
}

export interface SessionWithMessages extends Session {
  messages: Message[];
}

export type QueryType = 'COVERAGE_LOOKUP' | 'LCD_QUERY' | 'DENIAL_EXPLANATION' | 'PRIOR_AUTH' | 'GENERAL';
export type DataSource = 'STUBBED' | 'RAG';

export interface QueryResponse {
  message: Message;
  query_type: QueryType;
  confidence: number;
  data_source: DataSource;
}

export interface User {
  id: string;
  email: string;
  organization_id?: string;
  role: 'user' | 'admin';
}

export interface AuthResult {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: User;
}

export interface DataSourceInfo {
  type: DataSource;
  last_updated: string;
  coverage: string[];
}
