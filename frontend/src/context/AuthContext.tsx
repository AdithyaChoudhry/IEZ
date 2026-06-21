import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { authService } from '@/services/auth';
import type { User, LoginCredentials, RegisterData } from '@/types';

interface AuthContextType {
  user: User | null;
  role: string;
  loading: boolean;
  login: (credentials: LoginCredentials) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

function readCachedRole(): string {
  return localStorage.getItem('user_role') ?? 'Engineer';
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [role, setRole] = useState<string>(readCachedRole());
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadUser = async () => {
      if (authService.isAuthenticated()) {
        try {
          const userData = await authService.getCurrentUser();
          const cachedRole = localStorage.getItem('user_role') ?? 'Engineer';
          const cachedEmpId = localStorage.getItem('user_employee_id') ?? null;
          const cachedEmpName = localStorage.getItem('user_employee_name') ?? userData.username;
          setUser({ ...userData, role: cachedRole, employee_id: cachedEmpId, employee_name: cachedEmpName });
          setRole(cachedRole);
        } catch {
          authService.logout();
        }
      }
      setLoading(false);
    };
    loadUser();
  }, []);

  const login = async (credentials: LoginCredentials) => {
    await authService.login(credentials);
    const userData = await authService.getCurrentUser();
    const newRole = localStorage.getItem('user_role') ?? 'Engineer';
    const empId = localStorage.getItem('user_employee_id') ?? null;
    const empName = localStorage.getItem('user_employee_name') ?? userData.username;
    setUser({ ...userData, role: newRole, employee_id: empId, employee_name: empName });
    setRole(newRole);
  };

  const register = async (data: RegisterData) => {
    await authService.register(data);
    await login({ username: data.username, password: data.password });
  };

  const logout = () => {
    authService.logout();
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_employee_id');
    localStorage.removeItem('user_employee_name');
    setUser(null);
    setRole('Engineer');
  };

  return (
    <AuthContext.Provider value={{ user, role, loading, login, register, logout, isAuthenticated: !!user }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
}
