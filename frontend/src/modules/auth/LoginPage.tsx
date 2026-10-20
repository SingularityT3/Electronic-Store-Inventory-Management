import { useState, type FormEvent } from 'react';
import { Link, Navigate, useLocation, useNavigate, type Location } from 'react-router-dom';
import { ApiError } from '../../api';
import { useAuth } from './AuthContext';

export default function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const from = (useLocation().state as { from?: Location } | null)?.from;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Back to where the user was going, or their home page.
  const target = from ? `${from.pathname}${from.search}` : '/';

  if (user && !submitting) return <Navigate to={target} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      await login(username, password);
      navigate(target, { replace: true });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server. Try again.');
      setPassword('');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>ESIMS</h1>
        <p>Sign in to continue</p>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <label>
          Username or email
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        <button type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
        <Link to="/forgot-password">Forgot password?</Link>
      </form>
    </main>
  );
}
