import { Link, Outlet } from 'react-router-dom';
import { can, useAuth } from '../modules/auth';
import NotificationBell from './NotificationBell';
import Sidebar from './Sidebar';
import UserMenu from './UserMenu';

/**
 * The frame every signed-in screen renders in: header (brand, notification bell, user menu),
 * sidebar menu and the content area. Place it under `RequireAuth`.
 */
export default function AppLayout() {
  const { user } = useAuth();
  if (!user) return null;
  return (
    <div className="shell">
      <a className="skip-link" href="#content">
        Skip to content
      </a>
      <header className="shell-header">
        <Link to="/" className="brand">
          ESIMS
          <span className="brand-sub">Electronics Store Inventory</span>
        </Link>
        <div className="header-actions">
          {can(user, 'notifications.view') && <NotificationBell />}
          <UserMenu user={user} />
        </div>
      </header>
      <Sidebar user={user} />
      <main id="content" className="shell-content">
        <Outlet />
      </main>
    </div>
  );
}
