import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from './AuthContext';

/** Renders its children only for a signed-in user; otherwise redirects to the login page. */
export default function RequireAuth({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const location = useLocation();
  if (user === undefined) return <p className="loading">Loading…</p>;
  if (user === null) return <Navigate to="/login" replace state={{ from: location }} />;
  return children;
}
