import { useEffect, useState } from 'react';
import { ApiError, api } from '../api';
import { usePopover } from './usePopover';

interface Notification {
  id: number;
  type: string;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
}

export default function NotificationBell() {
  const { open, setOpen, ref } = usePopover<HTMLDivElement>();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    let active = true;
    setLoading(true);
    setError('');
    api<Notification[]>('/notifications')
      .then((rows) => active && setNotifications(rows))
      .catch((cause: unknown) => {
        if (active) {
          setError(cause instanceof ApiError ? cause.message : 'Could not load notifications.');
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [open]);

  return (
    <div className="popover" ref={ref}>
      <button
        type="button"
        className="header-button"
        aria-label="Notifications"
        aria-expanded={open}
        aria-controls="notifications-panel"
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">🔔</span>
      </button>
      {open && (
        <div
          id="notifications-panel"
          className="popover-panel"
          role="region"
          aria-label="Notifications"
        >
          {loading && <p>Loading notifications…</p>}
          {error && <p role="alert">{error}</p>}
          {!loading && !error && notifications.length === 0 && <p>No new notifications.</p>}
          {!loading && !error && notifications.length > 0 && (
            <ol aria-label="Notification history">
              {notifications.map((notification) => (
                <li key={notification.id}>
                  <p>{notification.title}</p>
                  <p>{notification.message}</p>
                  <time dateTime={notification.created_at}>
                    {new Date(notification.created_at).toLocaleString()}
                  </time>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
