/** Where a notification's links go. Shared by the bell panel and the notifications page. */

export interface NotificationLinks {
  product_id?: number;
  variant_id?: number | null;
  location_id?: number;
  purchase_order_id?: number;
  product_name?: string;
  sku?: string;
  variant_sku?: string | null;
  quantity?: number;
  threshold?: number;
}

interface LinkedNotification {
  type: 'low_stock' | 'out_of_stock' | 'po_status';
  title: string;
  links: NotificationLinks | null;
}

/** "View order" / "View product": the screen for the order or product the notification is about. */
export function notificationHref(
  notification: LinkedNotification,
  canManageProducts: boolean,
): string | null {
  const links = notification.links;
  if (!links) return null;
  if (notification.type === 'po_status') {
    return links.purchase_order_id ? `/purchase-orders?order=${links.purchase_order_id}` : null;
  }
  if (!links.product_id) return null;
  if (canManageProducts) return `/products/${links.product_id}`;
  // Staff cannot open product management, so they go to stock levels or product search.
  if (links.location_id) return '/stock';
  const name = notification.title.replace(/^(Low|Out of) stock: /, '').split(' (')[0];
  return `/products/search?q=${encodeURIComponent(name)}`;
}

/**
 * "Create PO" from a low/out-of-stock alert (FR2.3-ST-1): a draft for the item at the alert's
 * location. The quantity tops stock up to the default reorder-to level, twice the threshold
 * (SRS A-4); the manager can change it before saving.
 */
export function createPurchaseOrderHref(notification: LinkedNotification): string | null {
  const links = notification.links;
  if (notification.type === 'po_status' || !links?.product_id || !links.location_id) return null;
  const quantity = Math.max(2 * (links.threshold ?? 0) - (links.quantity ?? 0), 1);
  const params = new URLSearchParams({
    product_id: String(links.product_id),
    location_id: String(links.location_id),
    quantity: String(quantity),
  });
  if (links.product_name) params.set('product_name', links.product_name);
  if (links.sku) params.set('sku', links.sku);
  if (links.variant_id) params.set('variant_id', String(links.variant_id));
  if (links.variant_sku) params.set('variant_sku', links.variant_sku);
  return `/purchase-orders?${params.toString()}`;
}
