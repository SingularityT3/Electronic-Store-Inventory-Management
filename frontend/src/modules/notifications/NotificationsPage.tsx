import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../../api';
import { DataTable, EmptyState } from '../../shell/components';
import { useAuth, can } from '../auth';

interface Notification {
  id: number;
  type: 'low_stock' | 'out_of_stock' | 'po_status';
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
  location_id: number | null;
  location_name: string | null;
  reference_type: string | null;
  reference_id: number | null;
  links: {
    product_id?: number;
    variant_id?: number | null;
    location_id?: number;
    purchase_order_id?: number;
  } | null;
}

interface NotificationsResponse {
  items: Notification[];
  total: number;
}

const TYPE_LABELS: Record<string, string> = {
  low_stock: 'Low stock',
  out_of_stock: 'Out of stock',
  po_status: 'Order',
};

export default function NotificationsPage() {
  const { user } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [filter, setFilter] = useState<'all' | 'unread'>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  function buildUrl(
    path: string,
    params: Record<string, string | number | boolean | undefined>,
  ): string {
    const searchParams = new URLSearchParams();
    Object.entries(params).forEach(([key, value]) => {
      if (value !== undefined) {
        searchParams.append(key, String(value));
      }
    });
    const query = searchParams.toString();
    return query ? `${path}?${query}` : path;
  }

  const fetchNotifications = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api<NotificationsResponse>(
        buildUrl('/notifications', {
          limit: pageSize,
          offset: (page - 1) * pageSize,
          unread_only: filter === 'unread',
          include_read: filter === 'all',
        }),
      );
      setNotifications(response.items);
      setTotal(response.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notifications');
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, filter]);

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const handleMarkRead = async (id: number) => {
    const notif = notifications.find((n) => n.id === id);
    if (!notif) return;

    setNotifications((prev) =>
      prev.map((n) =>
        n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n,
      ),
    );

    try {
      await api(`/notifications/${id}/read`, { method: 'POST' });
    } catch (err) {
      setNotifications((prev) => prev.map((n) => (n.id === id ? notif : n)));
      setError(err instanceof Error ? err.message : 'Failed to mark as read');
    }
  };

  const handleMarkAllRead = async () => {
    const unread = notifications.filter((n) => !n.is_read);
    if (unread.length === 0) return;

    const now = new Date().toISOString();
    setNotifications((prev) =>
      prev.map((n) => (n.is_read ? n : { ...n, is_read: true, read_at: now })),
    );

    try {
      await api('/notifications/read-all', { method: 'POST' });
    } catch (err) {
      setNotifications((prev) =>
        prev.map((n) => {
          const original = unread.find((o) => o.id === n.id);
          return original ? original : n;
        }),
      );
      setError(err instanceof Error ? err.message : 'Failed to mark all as read');
    }
  };

  const handleDismiss = async (id: number) => {
    const notif = notifications.find((n) => n.id === id);
    if (!notif) return;

    setNotifications((prev) => prev.filter((n) => n.id !== id));

    try {
      await api(`/notifications/${id}/dismiss`, { method: 'POST' });
    } catch (err) {
      setNotifications((prev) =>
        [...prev, notif].sort(
          (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
        ),
      );
      setError(err instanceof Error ? err.message : 'Failed to dismiss');
    }
  };

  const handleLinkClick = (notification: Notification) => {
    if (!notification.is_read) {
      handleMarkRead(notification.id);
    }
  };

  const getNotificationLink = (notification: Notification): string | null => {
    if (!notification.links) return null;

    if (notification.type === 'po_status' && notification.links.purchase_order_id) {
      return `/purchase-orders/${notification.links.purchase_order_id}`;
    }

    if (
      (notification.type === 'low_stock' || notification.type === 'out_of_stock') &&
      notification.links.product_id
    ) {
      if (!can(user, 'products.manage')) {
        const locationId = notification.links.location_id;
        if (locationId) {
          return `/stock?product=${notification.links.product_id}&location=${locationId}`;
        }
        return `/products/search?q=${encodeURIComponent(
          notification.title
            .replace('Low stock: ', '')
            .replace('Out of stock: ', '')
            .split(' (')[0],
        )}`;
      }
      const variantPart = notification.links.variant_id
        ? `/variants/${notification.links.variant_id}`
        : '';
      return `/products/${notification.links.product_id}${variantPart}`;
    }

    return null;
  };

  const formatRelativeTime = (dateString: string): string => {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffSecs < 60) return 'just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffHours < 24) return `${diffHours}h ago`;
    if (diffDays < 7) return `${diffDays}d ago`;
    return date.toLocaleDateString();
  };

  const canViewNotifications = user && ['admin', 'manager', 'staff'].includes(user.role);

  if (!canViewNotifications) {
    return (
      <div className="page">
        <h1>Access Denied</h1>
        <p>You do not have permission to view notifications.</p>
      </div>
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <h1>Notifications</h1>
        {notifications.some((n) => !n.is_read) && (
          <button type="button" className="page-action" onClick={handleMarkAllRead}>
            Mark all as read
          </button>
        )}
      </header>

      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}

      <form className="audit-filters" aria-label="Filter notifications">
        <label>
          Filter
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value as 'all' | 'unread');
              setPage(1);
            }}
          >
            <option value="all">All</option>
            <option value="unread">Unread</option>
          </select>
        </label>
      </form>

      {loading ? (
        <p className="loading">Loading notifications…</p>
      ) : notifications.length === 0 ? (
        <EmptyState message={filter === 'unread' ? 'All caught up!' : 'No notifications yet.'} />
      ) : (
        <>
          <DataTable
            caption="Notifications"
            columns={[
              {
                header: 'Type',
                cell: (row: Notification) => (
                  <span className={`notification-type ${row.type}`}>
                    {TYPE_LABELS[row.type] || row.type}
                  </span>
                ),
              },
              {
                header: 'Title',
                cell: (row: Notification) => (
                  <strong className={!row.is_read ? 'unread' : ''}>{row.title}</strong>
                ),
              },
              {
                header: 'Message',
                cell: (row: Notification) => row.message,
              },
              {
                header: 'Time',
                cell: (row: Notification) => (
                  <time dateTime={row.created_at} title={new Date(row.created_at).toLocaleString()}>
                    {formatRelativeTime(row.created_at)}
                  </time>
                ),
              },
              {
                header: 'Actions',
                cell: (row: Notification) => {
                  const link = getNotificationLink(row);
                  return (
                    <div className="notification-actions">
                      {link && (
                        <Link
                          to={link}
                          className="notification-link"
                          onClick={() => handleLinkClick(row)}
                        >
                          {row.type === 'po_status' ? 'View order' : 'View product'}
                        </Link>
                      )}
                      {row.type !== 'po_status' &&
                        row.links?.product_id &&
                        can(user, 'purchase_orders.manage') && (
                          <>
                            {' | '}
                            <Link
                              to={`/purchase-orders/new?product=${row.links.product_id}&location=${row.links.location_id || ''}&variant=${row.links.variant_id || ''}`}
                              className="notification-link"
                              onClick={() => handleLinkClick(row)}
                            >
                              Create PO
                            </Link>
                          </>
                        )}
                      <div className="notification-controls">
                        {!row.is_read && (
                          <button
                            type="button"
                            className="notification-btn"
                            onClick={() => handleMarkRead(row.id)}
                            aria-label={`Mark "${row.title}" as read`}
                          >
                            Mark as read
                          </button>
                        )}
                        <button
                          type="button"
                          className="notification-btn dismiss"
                          onClick={() => handleDismiss(row.id)}
                          aria-label={`Dismiss "${row.title}"`}
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                  );
                },
              },
            ]}
            rows={notifications}
            rowKey={(row) => row.id}
            emptyMessage="No notifications match these filters."
          />

          {total > pageSize && (
            <nav className="pagination" aria-label="Pagination">
              <button
                type="button"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
                aria-label="Previous page"
              >
                Previous
              </button>
              <span className="pagination-info">
                Page {page} of {Math.ceil(total / pageSize)}
              </span>
              <button
                type="button"
                disabled={page * pageSize >= total}
                onClick={() => setPage(page + 1)}
                aria-label="Next page"
              >
                Next
              </button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}
