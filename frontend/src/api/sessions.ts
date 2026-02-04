import apiClient from './client';
import { Session, SessionWithMessages } from '../types';

export const sessionsApi = {
  list: async (): Promise<Session[]> => {
    const response = await apiClient.get<Session[]>('/sessions');
    return response.data;
  },

  get: async (sessionId: string): Promise<SessionWithMessages> => {
    const response = await apiClient.get<SessionWithMessages>(`/sessions/${sessionId}`);
    return response.data;
  },

  create: async (): Promise<Session> => {
    const response = await apiClient.post<Session>('/sessions');
    return response.data;
  },

  delete: async (sessionId: string): Promise<void> => {
    await apiClient.delete(`/sessions/${sessionId}`);
  },
};
