import { useRef } from 'react';
import { useAuth } from '../modules/auth';
import { NotificationPanel } from '../modules/notifications';

export default function NotificationBell() {
  const { user } = useAuth();
  const canViewNotifications = user && ['admin', 'manager', 'staff'].includes(user.role);
  const bellRef = useRef<HTMLButtonElement>(null);

  if (!canViewNotifications) return null;

  return <NotificationPanel bellRef={bellRef} />;
}
