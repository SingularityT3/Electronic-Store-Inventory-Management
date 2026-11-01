import { api } from '../../api';

export interface Notification {
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

export interface UnreadCount {
  unread: number;
}

export interface NotificationFilters {
  limit?: number;
  offset?: number;
  unread_only?: boolean;
  include_read?: boolean;
  [key: string]: string | number | boolean | undefined;
}

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

export const notificationsApi = {
  list: (filters: NotificationFilters = {}) =>
    api<Notification[]>(buildUrl('/notifications', filters)),

  unreadCount: () => api<UnreadCount>('/notifications/unread-count'),

  markRead: (id: number) => api(`/notifications/${id}/read`, { method: 'POST' }),

  markAllRead: () => api('/notifications/read-all', { method: 'POST' }),

  dismiss: (id: number) => api(`/notifications/${id}/dismiss`, { method: 'POST' }),
};
