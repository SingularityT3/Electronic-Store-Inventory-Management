import { useAuth } from '../modules/auth';
import { ROLE_NAMES } from './UserMenu';

/** Landing screen after sign in. The menu on the left lists what this role can do. */
export default function DashboardPage() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="page">
      <h1>{ROLE_NAMES[user.role]} dashboard</h1>
      <p>Welcome, {user.full_name}. Choose what you want to do from the menu on the left.</p>
    </div>
  );
}
