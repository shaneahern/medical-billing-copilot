import apiClient from './client';
import { QueryResponse } from '../types';

export const queryApi = {
  submit: async (sessionId: string, query: string): Promise<QueryResponse> => {
    const response = await apiClient.post<QueryResponse>('/query', {
      session_id: sessionId,
      query,
    });
    return response.data;
  },
};
