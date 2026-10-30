import { NavLink } from 'react-router-dom';
import { groupedMenuFor } from './navigation';
import type { User } from '../modules/auth';

/** The main menu: only the screens the signed-in role may use, in labelled groups. */
export default function Sidebar({ user }: { user: User }) {
  return (
    <nav className="sidebar" aria-label="Main menu">
      <NavLink to="/" end className="sidebar-link">
        Dashboard
      </NavLink>
      {groupedMenuFor(user).map((group) => (
        <div key={group.title} className="nav-group">
          <p className="nav-group-title" id={`nav-${group.title}`}>
            {group.title}
          </p>
          <ul aria-labelledby={`nav-${group.title}`}>
            {group.items.map((item) => (
              <li key={item.path}>
                <NavLink to={item.path} end={item.path !== '/reports'} className="sidebar-link">
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}
