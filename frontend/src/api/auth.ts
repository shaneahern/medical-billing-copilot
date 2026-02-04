import apiClient from './client';
import { AuthResult } from '../types';

export const authApi = {
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
