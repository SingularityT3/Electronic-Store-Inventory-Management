import { useRef } from 'react';
import { useAuth } from '../modules/auth';
import { NotificationPanel } from '../modules/notifications';

export default function NotificationBell() {
  const { user } = useAuth();
  const canViewNotifications = user && ['admin', 'manager', 'staff'].includes(user.role);

  if (!canViewNotifications) return null;

  const bellRef = useRef<HTMLButtonElement>(null);

  return <NotificationPanel bellRef={bellRef} />;
}