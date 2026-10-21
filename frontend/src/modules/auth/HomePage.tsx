import { Link, useNavigate } from 'react-router-dom';
import { can, useAuth } from './AuthContext';

const ROLE_NAMES = { admin: 'Admin', manager: 'Manager', staff: 'Staff', cashier: 'Cashier' };

/** Placeholder role dashboard until the UI shell (#4) replaces it. */
export default function HomePage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  if (!user) return null;

  async function signOut() {
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <main className="home">
      <header>
        <h1>{ROLE_NAMES[user.role]} dashboard</h1>
        <span>
          Signed in as {user.full_name} ({user.username})
        </span>
        <button onClick={signOut}>Sign out</button>
      </header>
      {can(user, 'audit.view') && (
        <nav className="home-links">
          <Link to="/audit">Audit log</Link>
        </nav>
      )}
    </main>
  );
}
