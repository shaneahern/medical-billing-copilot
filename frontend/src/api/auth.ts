import apiClient from './client';
import { AuthResult } from '../types';

export const authApi = {
  register: async (email: string, password: string, organizationId?: string): Promise<AuthResult> => {
    const response = await apiClient.post<AuthResult>('/auth/register', {
      email,
      password,
      organization_id: organizationId,
    });
    return response.data;
  },

  login: async (email: string, password: string): Promise<AuthResult> => {
    const response = await apiClient.post<AuthResult>('/auth/login', {
      email,
      password,
    });
    return response.data;
  },

  logout: async (): Promise<void> => {
    await apiClient.post('/auth/logout');
  },

  refresh: async (refreshToken: string): Promise<AuthResult> => {
    const response = await apiClient.post<AuthResult>('/auth/refresh', {
      refresh_token: refreshToken,
    });
    return response.data;
  },
};
