import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { usePopover } from '../../shell/usePopover';
import { useAuth } from '../auth';
import { useNotifications } from './useNotifications';
import { can } from '../auth';
import { formatRelativeTime } from '../../utils/date';
import { createPurchaseOrderHref, notificationHref } from './links';

interface NotificationPanelProps {
  bellRef: React.RefObject<HTMLButtonElement>;
}

export function NotificationPanel({ bellRef }: NotificationPanelProps) {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { open, setOpen, close } = usePopover<HTMLDivElement>();
  const { notifications, unreadCount, loading, error, markRead, markAllRead, dismiss } =
    useNotifications();
  const panelRef = useRef<HTMLDivElement>(null);

  // Handle escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && open) {
        close();
        bellRef.current?.focus();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [open, close, bellRef]);

  // Focus trap within panel
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusableElements = panel.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
    );
    const firstElement = focusableElements[0];
    const lastElement = focusableElements[focusableElements.length - 1];

    const handleTab = (e: KeyboardEvent) => {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === firstElement) {
          e.preventDefault();
          lastElement?.focus();
        }
      } else {
        if (document.activeElement === lastElement) {
          e.preventDefault();
          firstElement?.focus();
        }
      }
    };

    panel.addEventListener('keydown', handleTab);
    firstElement?.focus();
    return () => panel.removeEventListener('keydown', handleTab);
  }, [open]);

  const handleMarkRead = async (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await markRead(id);
    } catch {
      // Error handled in hook
    }
  };

  const handleDismiss = async (id: number, e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    try {
      await dismiss(id);
    } catch {
      // Error handled in hook
    }
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllRead();
    } catch {
      // Error handled in hook
    }
  };

  const handleLinkClick = async (
    notification: (typeof notifications)[0],
    href: string,
    e: React.MouseEvent,
  ) => {
    // Mark as read, then go there in the app (a plain link would reload the page).
    e.preventDefault();
    if (!notification.is_read) {
      try {
        await markRead(notification.id);
      } catch {
        // Navigate even if marking it read fails.
      }
    }
    close();
    navigate(href);
  };

  const getNotificationLink = (notification: (typeof notifications)[0]): string | null =>
    notificationHref(notification, can(user, 'products.manage'));

  if (!user) return null;

  return (
    <div className="popover" ref={panelRef}>
      <button
        type="button"
        className="header-button"
        ref={bellRef}
        aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
        aria-expanded={open}
        aria-controls="notifications-panel"
        aria-haspopup="dialog"
        onClick={() => setOpen(!open)}
      >
        <span aria-hidden="true">{'\u{1F514}'}</span>
        {unreadCount > 0 && (
          <span className="notification-badge" aria-hidden="true">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div
          id="notifications-panel"
          className="popover-panel notification-panel"
          role="region"
          aria-label="Notifications"
        >
          <header className="notification-panel-header">
            <h2>Notifications</h2>
            {unreadCount > 0 && (
              <button
                type="button"
                className="notification-mark-all"
                onClick={handleMarkAllRead}
                disabled={loading}
              >
                Mark all as read
              </button>
            )}
          </header>

          {loading && <div className="notification-loading">Loading notifications…</div>}

          {error && (
            <div className="notification-error" role="alert">
              {error}
            </div>
          )}

          {!loading && !error && notifications.length === 0 && (
            <div className="notification-empty">
              <p>No new notifications.</p>
            </div>
          )}

          {!loading && !error && notifications.length > 0 && (
            <ol className="notification-list" aria-label="Notification history">
              {notifications.map((notification) => {
                const link = getNotificationLink(notification);
                const isUnread = !notification.is_read;

                return (
                  <li
                    key={notification.id}
                    className={`notification-item ${isUnread ? 'unread' : ''}`}
                  >
                    <div className="notification-content">
                      <div className="notification-header-row">
                        <span className={`notification-type ${notification.type}`}>
                          {notification.type === 'low_stock'
                            ? 'Low stock'
                            : notification.type === 'out_of_stock'
                              ? 'Out of stock'
                              : 'Order'}
                        </span>
                        <time
                          className="notification-time"
                          dateTime={notification.created_at}
                          title={new Date(notification.created_at).toLocaleString()}
                        >
                          {formatRelativeTime(notification.created_at)}
                        </time>
                      </div>
                      <h3 className="notification-title">{notification.title}</h3>
                      <p className="notification-message">{notification.message}</p>

                      {link && (
                        <div className="notification-actions">
                          <a
                            href={link}
                            className="notification-link"
                            onClick={(e) => handleLinkClick(notification, link, e)}
                          >
                            {notification.type === 'po_status' ? 'View order' : 'View product'}
                          </a>
                          {createPurchaseOrderHref(notification) &&
                            can(user, 'purchase_orders.manage') && (
                              <>
                                {' | '}
                                <a
                                  href={createPurchaseOrderHref(notification) ?? undefined}
                                  className="notification-link"
                                  onClick={(e) =>
                                    handleLinkClick(
                                      notification,
                                      createPurchaseOrderHref(notification) ?? '/purchase-orders',
                                      e,
                                    )
                                  }
                                >
                                  Create PO
                                </a>
                              </>
                            )}
                          <div className="notification-controls">
                            {!notification.is_read && (
                              <button
                                type="button"
                                className="notification-btn"
                                onClick={(e) => handleMarkRead(notification.id, e)}
                                aria-label={`Mark "${notification.title}" as read`}
                              >
                                Mark as read
                              </button>
                            )}
                            <button
                              type="button"
                              className="notification-btn dismiss"
                              onClick={(e) => handleDismiss(notification.id, e)}
                              aria-label={`Dismiss "${notification.title}"`}
                            >
                              Dismiss
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          )}

          <footer className="notification-panel-footer">
            <a
              href="/notifications"
              className="notification-view-all"
              onClick={(e) => {
                e.preventDefault();
                close();
                window.location.href = '/notifications';
              }}
            >
              View all notifications
            </a>
          </footer>
        </div>
      )}
    </div>
  );
}
