import { useEffect, useRef, useState } from 'react';
import { usePopover } from '../../shell/usePopover';
import { useAuth } from '../auth';
import { useNotifications } from './useNotifications';
import { can } from '../auth';
import { formatRelativeTime } from '../../utils/date';

interface NotificationPanelProps {
  bellRef: React.RefObject<HTMLButtonElement>;
}

export function NotificationPanel({ bellRef }: NotificationPanelProps) {
  const { user } = useAuth();
  const { open, setOpen, close } = usePopover<HTMLDivElement>({ returnFocus: bellRef });
  const {
    notifications,
    unreadCount,
    loading,
    error,
    fetchNotifications,
    markRead,
    markAllRead,
    dismiss,
  } = useNotifications();
  const [showAll, setShowAll] = useState(false);
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
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
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

  const handleLinkClick = async (notification: typeof notifications[0], e: React.MouseEvent) => {
    // Mark as read when clicking a link
    if (!notification.is_read) {
      e.preventDefault();
      try {
        await markRead(notification.id);
      } catch {
        // Continue with navigation even if mark read fails
      }
    }
  };

  const getNotificationLink = (notification: typeof notifications[0]): string | null => {
    if (!notification.links) return null;

    if (notification.type === 'po_status' && notification.links.purchase_order_id) {
      return `/purchase-orders/${notification.links.purchase_order_id}`;
    }

    if (
      (notification.type === 'low_stock' || notification.type === 'out_of_stock') &&
      notification.links.product_id
    ) {
      // For staff who can't access product management, link to stock levels or product search
      if (!can(user, 'products.manage')) {
        const locationId = notification.links.location_id;
        if (locationId) {
          return `/stock?product=${notification.links.product_id}&location=${locationId}`;
        }
        return `/products/search?q=${encodeURIComponent(notification.title.replace('Low stock: ', '').replace('Out of stock: ', '').split(' (')[0])}`;
      }
      const variantPart = notification.links.variant_id ? `/variants/${notification.links.variant_id}` : '';
      return `/products/${notification.links.product_id}${variantPart}`;
    }

    return null;
  };

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
        <span aria-hidden="true">🔔</span>
        {unreadCount > 0 && (
          <span
            className="notification-badge"
            aria-hidden="true"
          >
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

          {error && <div className="notification-error" role="alert">{error}</div>}

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
                            onClick={(e) => handleLinkClick(notification, e)}
                          >
                            {notification.type === 'po_status' ? 'View order' : 'View product'}
                          </a>
                          {notification.type !== 'po_status' &&
                            notification.links?.product_id &&
                            can(user, 'purchase_orders.manage') && (
                              <>
                                {' | '}
                                <a
                                  href={`/purchase-orders/new?product=${notification.links.product_id}&location=${notification.links.location_id || ''}&variant=${notification.links.variant_id || ''}`}
                                  className="notification-link"
                                  onClick={(e) => handleLinkClick(notification, e)}
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