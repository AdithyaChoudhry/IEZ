/**
 * Authentication service - handles login, register, logout operations.
 */
import api from './api';
import type { LoginCredentials, RegisterData, TokenResponse, User } from '@/types';

export const authService = {
  /**
   * Login with username and password.
   */
  async login(credentials: LoginCredentials): Promise<TokenResponse> {
    const response = await api.post<TokenResponse>('/auth/login', credentials);
    const { access_token, refresh_token, role, employee_id, employee_name } = response.data as any;

    localStorage.setItem('access_token', access_token);
    localStorage.setItem('refresh_token', refresh_token);
    // Cache role info so AuthContext can read it without an extra API round-trip
    localStorage.setItem('user_role', role ?? 'Engineer');
    localStorage.setItem('user_employee_id', employee_id ?? '');
    localStorage.setItem('user_employee_name', employee_name ?? '');

    return response.data;
  },

  /**
   * Register a new user account.
   */
  async register(data: RegisterData): Promise<User> {
    const response = await api.post<User>('/auth/register', data);
    return response.data;
  },

  /**
   * Get current authenticated user info.
   */
  async getCurrentUser(): Promise<User> {
    const response = await api.get<User>('/auth/me');
    return response.data;
  },

  /**
   * Logout and clear tokens.
   */
  logout(): void {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    // Optionally call logout endpoint
    api.post('/auth/logout').catch(() => {
      // Ignore errors on logout
    });
  },

  /**
   * Check if user is authenticated (has valid token).
   */
  isAuthenticated(): boolean {
    return !!localStorage.getItem('access_token');
  },
};
