import { useNavigate } from 'react-router-dom';
import type { Role, User } from '../modules/auth';
import { useAuth } from '../modules/auth';
import { usePopover } from './usePopover';

export const ROLE_NAMES: Record<Role, string> = {
  admin: 'Admin',
  manager: 'Manager',
  staff: 'Staff',
  cashier: 'Cashier',
};

/** The signed-in user's name with a menu holding their role and the sign out action. */
export default function UserMenu({ user }: { user: User }) {
  const { logout } = useAuth();
  const navigate = useNavigate();
  const { open, setOpen, ref } = usePopover<HTMLDivElement>();

  async function signOut() {
    setOpen(false);
    await logout();
    navigate('/login', { replace: true });
  }

  return (
    <div className="popover" ref={ref}>
      <button
        type="button"
        className="header-button"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
      >
        {user.full_name} <span aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="popover-panel user-menu" role="menu" aria-label="User menu">
          <p className="user-menu-info">
            Signed in as <strong>{user.username}</strong>
            <br />
            Role: {ROLE_NAMES[user.role]}
          </p>
          <button type="button" role="menuitem" onClick={signOut}>
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}
