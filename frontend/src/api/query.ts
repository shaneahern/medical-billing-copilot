import apiClient from './client';
import { QueryResponse } from '../types';

export interface DataSourceInfo {
  type: string;
  is_stubbed: boolean;
  is_rag: boolean;
  is_live: boolean;
  has_policy_data: boolean;
  policy_doc_count: number;
  last_updated: string;
  coverage: string[];
  display_message: string;
}

export const queryApi = {
  submit: async (sessionId: string, query: string): Promise<QueryResponse> => {
    const response = await apiClient.post<QueryResponse>('/query', {
      session_id: sessionId,
      query,
    });
    return response.data;
  },

  getDataSourceInfo: async (): Promise<DataSourceInfo> => {
    const response = await apiClient.get<DataSourceInfo>('/data-source');
    return response.data;
  },
};
