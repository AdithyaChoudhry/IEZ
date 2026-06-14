/**
 * TypeScript interfaces for authentication and API responses.
 */

export interface User {
  id: number;
  email: string;
  username: string;
  is_active: boolean;
  is_superuser: boolean;
  created_at: string;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface RegisterData {
  email: string;
  username: string;
  password: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface ApiError {
  detail: string;
}

// Module-specific types
export interface ValidationError {
  row: number;
  sno: string;
  tag: string;
  column: string;
  cell: string;
  message: string;
  rule: number | string;
  rule_name?: string;
  rule_type?: string;
  source?: string;
}

export interface MappingLog {
  tag: string;
  heading: string;
  iodb_col: string;
  score: number;
  value: string;
  status: string;
}

export interface ProgressUpdate {
  current: number;
  total: number;
  status: string;
  message?: string;
}
