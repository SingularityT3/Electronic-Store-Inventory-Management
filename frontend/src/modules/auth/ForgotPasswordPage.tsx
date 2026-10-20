import { useState, type FormEvent } from 'react';
import { Link } from 'react-router-dom';
import { api, ApiError } from '../../api';

export default function ForgotPasswordPage() {
  const [username, setUsername] = useState('');
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    try {
      const result = await api<{ detail: string }>('/auth/password-reset/request', {
        body: { username },
      });
      setMessage(result.detail);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not reach the server. Try again.');
    }
  }

  return (
    <main className="auth-page">
      <form className="auth-card" onSubmit={submit}>
        <h1>Reset password</h1>
        {message ? (
          <p role="status">{message}</p>
        ) : (
          <>
            <p>Enter your username or email. We will email you a link to choose a new password.</p>
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
                required
              />
            </label>
            <button type="submit">Send reset link</button>
          </>
        )}
        <Link to="/login">Back to sign in</Link>
      </form>
    </main>
  );
}
