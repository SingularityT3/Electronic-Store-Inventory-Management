import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../App';
import { AuthProvider, type Permission, type Role, type User } from '../modules/auth';

/**
 * The permissions each role holds, as the backend grants them (ROLE_PERMISSIONS in
 * backend/app/modules/auth/_internal/permissions.py). Keep in step with it.
 */
const ALL: Permission[] = [
  'users.manage',
  'audit.view',
  'products.view',
  'products.manage',
  'stock.view',
  'stock.adjust',
  'stock.transfer',
  'suppliers.manage',
  'purchase_orders.manage',
  'purchase_orders.receive',
  'sales.record',
  'returns.approve_late',
  'reports.view',
  'notifications.view',
];

const PERMISSIONS: Record<Role, Permission[]> = {
  admin: ALL,
  manager: ALL.filter((p) => p !== 'users.manage' && p !== 'audit.view'),
  staff: [
    'products.view',
    'stock.view',
    'stock.adjust',
    'stock.transfer',
    'purchase_orders.receive',
    'notifications.view',
  ],
  cashier: ['products.view', 'sales.record'],
};

function userWithRole(role: Role): User {
  return {
    id: 1,
    username: `${role}_user`,
    full_name: `Test ${role}`,
    role,
    location_id: role === 'staff' || role === 'cashier' ? 1 : null,
    permissions: PERMISSIONS[role],
  };
}

function signedInAs(role: Role) {
  const reply = (status: number, body?: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      url === '/api/auth/me' ? reply(200, userWithRole(role)) : reply(404, { detail: 'Not found' }),
    ),
  );
}

function renderAt(path: string) {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function menuLabels(): Promise<string[]> {
  const nav = await screen.findByRole('navigation', { name: 'Main menu' });
  return within(nav)
    .getAllByRole('link')
    .map((link) => link.textContent ?? '');
}

// FR5.1-IT-3: each role sees exactly its permitted menu items, no more and no fewer.
const EXPECTED_MENU: Record<Role, string[]> = {
  admin: [
    'Dashboard',
    'Products',
    'Categories',
    'Variants',
    'Stock levels',
    'Stock adjustment',
    'Stock transfer',
    'Suppliers',
    'Purchase orders',
    'PO receiving',
    'Sales',
    'Returns',
    'Reports',
    'User management',
    'Audit log',
  ],
  manager: [
    'Dashboard',
    'Products',
    'Categories',
    'Variants',
    'Stock levels',
    'Stock adjustment',
    'Stock transfer',
    'Suppliers',
    'Purchase orders',
    'PO receiving',
    'Sales',
    'Returns',
    'Reports',
  ],
  staff: [
    'Dashboard',
    'Product search',
    'Stock levels',
    'Stock adjustment',
    'Stock transfer',
    'PO receiving',
  ],
  cashier: ['Dashboard', 'Product search', 'Sales', 'Returns'],
};

test.each(Object.keys(EXPECTED_MENU) as Role[])(
  'the %s menu shows exactly its items',
  async (role) => {
    signedInAs(role);
    renderAt('/');
    expect(await menuLabels()).toEqual(EXPECTED_MENU[role]);
  },
);

test('the shell has a header, a menu and a content area', async () => {
  signedInAs('manager');
  renderAt('/');
  await screen.findByRole('heading', { name: 'Manager dashboard' });
  expect(screen.getByRole('banner')).toHaveTextContent('ESIMS');
  expect(screen.getByRole('navigation', { name: 'Main menu' })).toBeInTheDocument();
  expect(screen.getByRole('main')).toBeInTheDocument();
});

test('the current screen is marked in the menu', async () => {
  signedInAs('manager');
  renderAt('/suppliers');
  await screen.findByRole('heading', { name: 'Suppliers' });
  expect(screen.getByRole('link', { name: 'Suppliers' })).toHaveAttribute('aria-current', 'page');
  expect(screen.getByRole('link', { name: 'Dashboard' })).not.toHaveAttribute('aria-current');
});

test('a menu link opens its screen', async () => {
  signedInAs('cashier');
  renderAt('/');
  await userEvent.click(await screen.findByRole('link', { name: 'Returns' }));
  expect(await screen.findByRole('heading', { name: 'Returns' })).toBeInTheDocument();
});

// FR1.1-ST-2, FR1.2-ST-2, FR3.1-ST-2, FR5.1-ST-2, FR5.3-ST-2: a URL typed by hand is still blocked.
test.each([
  ['cashier', '/suppliers', 'supplier management'],
  ['staff', '/categories', 'category management'],
  ['staff', '/purchase-orders', 'purchase orders'],
  ['manager', '/users', 'user management'],
  ['manager', '/audit', 'the audit log'],
  ['cashier', '/products/new', 'product management'],
] as [Role, string, string][])(
  '%s opening %s sees the access-denied page',
  async (role, path, what) => {
    signedInAs(role);
    renderAt(path);
    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      `You do not have permission to view ${what}.`,
    );
  },
);

test('cashier can open the products catalog', async () => {
  signedInAs('cashier');
  renderAt('/products');
  expect(await screen.findByRole('heading', { name: 'Products' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Access denied' })).not.toBeInTheDocument();
});

test('a permitted role opens the screen', async () => {
  signedInAs('admin');
  renderAt('/users');
  expect(await screen.findByRole('heading', { name: 'User management' })).toBeInTheDocument();
  expect(screen.queryByRole('heading', { name: 'Access denied' })).not.toBeInTheDocument();
});

test('an unknown URL shows page not found inside the shell', async () => {
  signedInAs('staff');
  renderAt('/no-such-page');
  expect(await screen.findByRole('heading', { name: 'Page not found' })).toBeInTheDocument();
  expect(screen.getByRole('navigation', { name: 'Main menu' })).toBeInTheDocument();
});

test('the user menu shows the name and role and offers Sign out', async () => {
  signedInAs('staff');
  renderAt('/');
  await userEvent.click(await screen.findByRole('button', { name: /Test staff/ }));
  const menu = screen.getByRole('menu', { name: 'User menu' });
  expect(menu).toHaveTextContent('Role: Staff');
  expect(within(menu).getByRole('menuitem', { name: 'Sign out' })).toBeInTheDocument();
});

test('Escape closes the user menu', async () => {
  signedInAs('staff');
  renderAt('/');
  await userEvent.click(await screen.findByRole('button', { name: /Test staff/ }));
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('menu')).not.toBeInTheDocument();
});

// SRS A-6: Cashiers receive no notifications, so they get no bell.
test.each([
  ['admin', true],
  ['manager', true],
  ['staff', true],
  ['cashier', false],
] as [Role, boolean][])('the %s header notification bell: %s', async (role, shown) => {
  signedInAs(role);
  renderAt('/');
  await screen.findByRole('heading', { name: /dashboard/ });
  const bell = screen.queryByRole('button', { name: 'Notifications' });
  expect(Boolean(bell)).toBe(shown);
});

test('the notification bell opens an empty placeholder panel', async () => {
  signedInAs('manager');
  renderAt('/');
  await userEvent.click(await screen.findByRole('button', { name: 'Notifications' }));
  expect(screen.getByRole('region', { name: 'Notifications' })).toHaveTextContent(
    'No new notifications.',
  );
});
