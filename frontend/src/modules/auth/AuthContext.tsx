import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { api, SESSION_EXPIRED_EVENT } from '../../api';

export type Role = 'admin' | 'manager' | 'staff' | 'cashier';

/** Mirrors the backend `Permission` enum (backend/app/modules/auth/service.py). */
export type Permission =
  | 'users.manage'
  | 'audit.view'
  | 'products.view'
  | 'products.manage'
  | 'stock.view'
  | 'stock.adjust'
  | 'stock.transfer'
  | 'suppliers.manage'
  | 'purchase_orders.manage'
  | 'purchase_orders.receive'
  | 'sales.record'
  | 'returns.approve_late'
  | 'reports.view'
  | 'notifications.view';

export interface User {
  id: number;
  username: string;
  full_name: string;
  role: Role;
  location_id: number | null;
  /** What the user's role may do. The server enforces these; the UI only hides what is denied. */
  permissions: Permission[];
}

/** Whether `user` may do `permission`, for showing or hiding menu items and actions. */
export function can(user: User | null | undefined, permission: Permission): boolean {
  return user?.permissions.includes(permission) ?? false;
}

interface AuthState {
  /** The signed-in user, null when signed out, undefined while still checking. */
  user: User | null | undefined;
  login(username: string, password: string): Promise<User>;
  logout(): Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null | undefined>(undefined);

  useEffect(() => {
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => setUser(null));
    // Any request rejected for an expired session signs the user out, so the
    // protected route sends them to the login page before the action proceeds.
    const expire = () => setUser(null);
    window.addEventListener(SESSION_EXPIRED_EVENT, expire);
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, expire);
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    const signedIn = await api<User>('/auth/login', { body: { username, password } });
    setUser(signedIn);
    return signedIn;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' });
    } finally {
      setUser(null);
    }
  }, []);

  return <AuthContext.Provider value={{ user, login, logout }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const auth = useContext(AuthContext);
  if (!auth) throw new Error('useAuth must be used inside AuthProvider');
  return auth;
}
