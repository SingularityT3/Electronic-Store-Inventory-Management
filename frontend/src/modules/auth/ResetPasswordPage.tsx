import { useState, type FormEvent } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, ApiError } from '../../api';

const MIN_LENGTH = 8;

export default function ResetPasswordPage() {
  const token = useSearchParams()[0].get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (password !== confirm) {
      setError('The passwords do not match.');
      return;
    }
    setError('');
    try {
      await api('/auth/password-reset/confirm', { body: { token, new_password: password } });
      setDone(true);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server. Try again.');
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>Choose a new password</h1>
        {done ? (
          <p role="status">Your password has been changed. Sign in with the new password.</p>
        ) : (
          <>
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            <label>
              New password
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                minLength={MIN_LENGTH}
                required
              />
            </label>
            <label>
              Confirm new password
              <input
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                minLength={MIN_LENGTH}
                required
              />
            </label>
            <button type="submit" disabled={!token}>
              Change password
            </button>
          </>
        )}
        <Link to="/login">Back to sign in</Link>
      </form>
    </main>
  );
}
