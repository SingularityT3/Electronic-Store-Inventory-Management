import type { Permission } from '../modules/auth';

export interface NavItem {
  path: string;
  label: string;
  group: string;
  /** What the role needs to open the screen. The server enforces it too (NFR-7). */
  permission: Permission;
  /** Finishes "You do not have permission to view ..." on the access-denied page. */
  deniedLabel: string;
  /** Left out of the menu for users who hold this permission, because a fuller screen covers it. */
  hiddenWith?: Permission;
}

/**
 * Every screen that appears in the menu, grouped as the sidebar shows it. Who sees what follows
 * the SRS role definitions (2.3, A-5, A-6, A-10) through the permissions the server sends, so
 * a role change on the backend needs no change here.
 *
 * Menu hiding is cosmetic: each route is also guarded by `RequirePermission`, and the API
 * answers 403 whatever the UI shows (NFR-7).
 */
export const NAV_ITEMS: NavItem[] = [
  {
    path: '/products',
    label: 'Products',
    group: 'Catalog',
    permission: 'products.manage',
    deniedLabel: 'product management',
  },
  {
    path: '/categories',
    label: 'Categories',
    group: 'Catalog',
    permission: 'products.manage',
    deniedLabel: 'category management',
  },
  {
    path: '/variants',
    label: 'Variants',
    group: 'Catalog',
    permission: 'products.manage',
    deniedLabel: 'product variants',
  },
  {
    path: '/products/search',
    label: 'Product search',
    group: 'Catalog',
    permission: 'products.view',
    deniedLabel: 'product search',
    hiddenWith: 'products.manage',
  },
  {
    path: '/stock',
    label: 'Stock levels',
    group: 'Inventory',
    permission: 'stock.view',
    deniedLabel: 'stock levels',
  },
  {
    path: '/stock/adjust',
    label: 'Stock adjustment',
    group: 'Inventory',
    permission: 'stock.adjust',
    deniedLabel: 'stock adjustments',
  },
  {
    path: '/stock/transfer',
    label: 'Stock transfer',
    group: 'Inventory',
    permission: 'stock.transfer',
    deniedLabel: 'stock transfers',
  },
  {
    path: '/suppliers',
    label: 'Suppliers',
    group: 'Purchasing',
    permission: 'suppliers.manage',
    deniedLabel: 'supplier management',
  },
  {
    path: '/purchase-orders',
    label: 'Purchase orders',
    group: 'Purchasing',
    permission: 'purchase_orders.manage',
    deniedLabel: 'purchase orders',
  },
  {
    path: '/purchase-orders/receive',
    label: 'PO receiving',
    group: 'Purchasing',
    permission: 'purchase_orders.receive',
    deniedLabel: 'purchase order receiving',
  },
  {
    path: '/sales',
    label: 'Sales',
    group: 'Sales and returns',
    permission: 'sales.record',
    deniedLabel: 'sales',
  },
  {
    path: '/returns',
    label: 'Returns',
    group: 'Sales and returns',
    permission: 'sales.record',
    deniedLabel: 'returns',
  },
  {
    path: '/reports',
    label: 'Reports',
    group: 'Reporting',
    permission: 'reports.view',
    deniedLabel: 'reports',
  },
  {
    path: '/users',
    label: 'User management',
    group: 'Administration',
    permission: 'users.manage',
    deniedLabel: 'user management',
  },
  {
    path: '/audit',
    label: 'Audit log',
    group: 'Administration',
    permission: 'audit.view',
    deniedLabel: 'the audit log',
  },
];

interface Holder {
  permissions: Permission[];
}

/** The menu items `user` may see, in menu order. */
export function menuFor(user: Holder): NavItem[] {
  const has = (p: Permission) => user.permissions.includes(p);
  return NAV_ITEMS.filter(
    (item) => has(item.permission) && !(item.hiddenWith && has(item.hiddenWith)),
  );
}

/** Menu items split into the sidebar's labelled groups, keeping menu order. */
export function groupedMenuFor(user: Holder): { title: string; items: NavItem[] }[] {
  const groups: { title: string; items: NavItem[] }[] = [];
  for (const item of menuFor(user)) {
    const last = groups.at(-1);
    if (last && last.title === item.group) last.items.push(item);
    else groups.push({ title: item.group, items: [item] });
  }
  return groups;
}
