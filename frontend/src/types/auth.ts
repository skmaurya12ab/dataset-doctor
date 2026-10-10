/**
 * TypeScript interfaces for authentication, user identity, and session security.
 */

export interface User {
  id: string;
  email: string;
  is_active: boolean;
  is_verified: boolean;
  role: string;
  created_at: string;
}

export interface LoginResponse {
  user: User;
  message: string;
  csrf_token: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface VerifyEmailRequest {
  token: string;
}

export interface ForgotPasswordRequest {
  email: string;
}

export interface ResetPasswordRequest {
  token: string;
  new_password: string;
}

export interface MessageResponse {
  message: string;
  success: boolean;
}
