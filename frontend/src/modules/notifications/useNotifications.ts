import { useEffect, useState, useCallback, useRef } from 'react';
import { notificationsApi, Notification, UnreadCount } from './api';
import { useAuth } from '../auth';

export function useNotifications() {
  const { user, loading: authLoading } = useAuth();
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const lastUserIdRef = useRef<number | null>(null);

  const fetchNotifications = useCallback(async () => {
    if (!user) return;
    try {
      const [notifs, count] = await Promise.all([
        notificationsApi.list({ limit: 10 }),
        notificationsApi.unreadCount(),
      ]);
      setNotifications(notifs);
      setUnreadCount(count.unread);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load notifications');
    } finally {
      setLoading(false);
    }
  }, [user]);

  const fetchUnreadCount = useCallback(async () => {
    if (!user) return;
    try {
      const count = await notificationsApi.unreadCount();
      setUnreadCount(count.unread);
    } catch {
      // Silently ignore count errors
    }
  }, [user]);

  // Start/stop polling
  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }

    if (user) {
      // Poll every 60 seconds while tab is visible
      pollingRef.current = window.setInterval(() => {
        if (!document.hidden) {
          fetchUnreadCount();
        }
      }, 60_000);
    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [user, fetchUnreadCount]);

  // Fetch on mount, user change, and when window regains focus
  useEffect(() => {
    if (authLoading) return;

    // Reset state when user changes
    if (user?.id !== lastUserIdRef.current) {
      setNotifications([]);
      setUnreadCount(0);
      setLoading(true);
      lastUserIdRef.current = user?.id ?? null;
    }

    if (user) {
      fetchNotifications();
    } else {
      setLoading(false);
    }
  }, [user, authLoading, fetchNotifications]);

  // Refresh on window focus
  useEffect(() => {
    const handleFocus = () => {
      if (user && !document.hidden) {
        fetchNotifications();
      }
    };
    window.addEventListener('focus', handleFocus);
    return () => window.removeEventListener('focus', handleFocus);
  }, [user, fetchNotifications]);

  const markRead = async (id: number) => {
    const notif = notifications.find(n => n.id === id);
    if (!notif) return;

    // Optimistic update
    setNotifications(prev =>
      prev.map(n =>
        n.id === id ? { ...n, is_read: true, read_at: new Date().toISOString() } : n
      )
    );
    setUnreadCount(prev => Math.max(0, prev - (notif.is_read ? 0 : 1)));

    try {
      await notificationsApi.markRead(id);
    } catch (err) {
      // Rollback
      setNotifications(prev =>
        prev.map(n => (n.id === id ? notif : n))
      );
      setUnreadCount(prev => prev + (notif.is_read ? 0 : 1));
      setError(err instanceof Error ? err.message : 'Failed to mark as read');
      throw err;
    }
  };

  const markAllRead = async () => {
    const unread = notifications.filter(n => !n.is_read);
    if (unread.length === 0) return;

    // Optimistic update
    const now = new Date().toISOString();
    setNotifications(prev =>
      prev.map(n =>
        n.is_read ? n : { ...n, is_read: true, read_at: now }
      )
    );
    setUnreadCount(0);

    try {
      await notificationsApi.markAllRead();
    } catch (err) {
      // Rollback
      setNotifications(prev =>
        prev.map(n => {
          const original = unread.find(o => o.id === n.id);
          return original ? original : n;
        })
      );
      setUnreadCount(unread.length);
      setError(err instanceof Error ? err.message : 'Failed to mark all as read');
      throw err;
    }
  };

  const dismiss = async (id: number) => {
    const notif = notifications.find(n => n.id === id);
    if (!notif) return;

    // Optimistic update
    setNotifications(prev => prev.filter(n => n.id !== id));
    setUnreadCount(prev => Math.max(0, prev - (notif.is_read ? 0 : 1)));

    try {
      await notificationsApi.dismiss(id);
    } catch (err) {
      // Rollback
      setNotifications(prev => [...prev, notif].sort((a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      ));
      setUnreadCount(prev => prev + (notif.is_read ? 0 : 1));
      setError(err instanceof Error ? err.message : 'Failed to dismiss');
      throw err;
    }
  };

  return {
    notifications,
    unreadCount,
    loading,
    error,
    fetchNotifications,
    markRead,
    markAllRead,
    dismiss,
  };
}