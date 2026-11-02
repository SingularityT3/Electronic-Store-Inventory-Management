import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Permission, type User } from '../auth';
import { createPurchaseOrderHref, notificationHref } from './links';

const LOW_STOCK = {
  id: 1,
  type: 'low_stock' as const,
  title: 'Low stock: Phone (PHONE-20)',
  message: 'Phone at Central Warehouse: 3 left (threshold 5).',
  is_read: false,
  created_at: '2026-11-01T10:00:00Z',
  location_id: 2,
  location_name: 'Central Warehouse',
  reference_type: 'stock_alert',
  reference_id: 9,
  links: {
    product_id: 20,
    variant_id: null,
    location_id: 2,
    product_name: 'Phone',
    sku: 'PHONE-20',
    variant_sku: null,
    quantity: 3,
    threshold: 5,
  },
};

const PO_STATUS = {
  ...LOW_STOCK,
  id: 2,
  type: 'po_status' as const,
  title: 'Purchase order status changed',
  message: 'PO-31: Submitted',
  is_read: true,
  location_id: null,
  location_name: null,
  reference_type: 'purchase_order',
  reference_id: 31,
  links: { purchase_order_id: 31 },
};

const ORDER = {
  id: 31,
  po_number: 'PO-31',
  supplier_id: 5,
  supplier_name: 'Northwind Supply',
  location_id: 2,
  status: 'submitted',
  created_by: 1,
  notes: null,
  expected_delivery_date: '2026-11-12',
  submitted_at: '2026-11-01T10:00:00Z',
  created_at: '2026-11-01T09:00:00Z',
  lines: [],
  total: '0.00',
};

const MANAGER: Permission[] = [
  'products.view',
  'products.manage',
  'purchase_orders.manage',
  'suppliers.manage',
  'stock.view',
  'notifications.view',
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function signedIn(permissions: Permission[] = MANAGER) {
  const user: User = {
    id: 1,
    username: 'manager',
    full_name: 'Test manager',
    role: 'manager',
    location_id: null,
    permissions,
  };
  const reply = (status: number, body?: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === '/api/auth/me') return reply(200, user);
      if (url === '/api/notifications/unread-count') return reply(200, { unread: 1 });
      if (url.startsWith('/api/notifications?')) return reply(200, [LOW_STOCK, PO_STATUS]);
      if (url === '/api/notifications/1/read') return reply(204);
      if (url === '/api/purchasing/purchase-orders') return reply(200, [ORDER]);
      if (url === '/api/purchasing/purchase-orders/31') return reply(200, ORDER);
      if (url === '/api/purchasing/suppliers?active_only=true') return reply(200, []);
      if (url === '/api/stock/locations') {
        return reply(200, [{ id: 2, name: 'Central Warehouse', type: 'warehouse' }]);
      }
      if (url.startsWith('/api/product/20')) return reply(404, { detail: 'Not found' });
      return reply(404, { detail: 'Not found' });
    }),
  );
  return calls;
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

test('links point at screens that exist and the Create PO link carries a suggested draft', () => {
  expect(notificationHref(LOW_STOCK, true)).toBe('/products/20');
  expect(notificationHref(LOW_STOCK, false)).toBe('/stock');
  expect(notificationHref(PO_STATUS, true)).toBe('/purchase-orders?order=31');
  expect(createPurchaseOrderHref(PO_STATUS)).toBeNull();
  const href = new URL(createPurchaseOrderHref(LOW_STOCK) ?? '', 'http://esims.test');
  expect(href.pathname).toBe('/purchase-orders');
  expect(Object.fromEntries(href.searchParams)).toEqual({
    product_id: '20',
    location_id: '2',
    quantity: '7',
    product_name: 'Phone',
    sku: 'PHONE-20',
  });
});

// FR2.3-ST-1: the manager acts on a low-stock alert by raising a purchase order from it.
test('the notifications page lists alerts and Create PO opens a prefilled draft', async () => {
  const user = userEvent.setup();
  signedIn();
  renderAt('/notifications');

  expect(await screen.findByRole('heading', { name: 'Notifications' })).toBeInTheDocument();
  const table = await screen.findByRole('table');
  expect(within(table).getByText('Low stock: Phone (PHONE-20)')).toBeInTheDocument();
  expect(within(table).getByText('PO-31: Submitted')).toBeInTheDocument();

  await user.click(within(table).getByRole('link', { name: 'Create PO' }));

  expect(await screen.findByRole('heading', { name: 'Purchase orders' })).toBeInTheDocument();
  expect(screen.getByLabelText('Receiving location')).toHaveValue('2');
  expect(screen.getByLabelText('Quantity PHONE-20')).toHaveValue(7);
});

test('View order on a PO notification opens that purchase order', async () => {
  const user = userEvent.setup();
  signedIn();
  renderAt('/notifications');

  const table = await screen.findByRole('table');
  await user.click(within(table).getByRole('link', { name: 'View order' }));

  expect(await screen.findByRole('heading', { name: 'PO-31 · submitted' })).toBeInTheDocument();
});

test('a link in the bell panel marks the notification read and then navigates', async () => {
  const user = userEvent.setup();
  const calls = signedIn();
  renderAt('/');

  await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }));
  const panel = await screen.findByRole('region', { name: 'Notifications' });
  await user.click(await within(panel).findByRole('link', { name: 'Create PO' }));

  await waitFor(() =>
    expect(calls.some((call) => call.url === '/api/notifications/1/read')).toBe(true),
  );
  expect(await screen.findByRole('heading', { name: 'Purchase orders' })).toBeInTheDocument();
  expect(screen.getByLabelText('Quantity PHONE-20')).toHaveValue(7);
});

// FR8.1-UT-3: a notification can be marked read or dismissed.
test('the panel marks a notification read and dismisses another', async () => {
  const user = userEvent.setup();
  const calls = signedIn();
  renderAt('/');

  await user.click(await screen.findByRole('button', { name: 'Notifications, 1 unread' }));
  const panel = await screen.findByRole('region', { name: 'Notifications' });
  await user.click(
    await within(panel).findByRole('button', { name: `Mark "${LOW_STOCK.title}" as read` }),
  );
  await waitFor(() =>
    expect(calls.some((call) => call.url === '/api/notifications/1/read')).toBe(true),
  );
  await user.click(within(panel).getByRole('button', { name: `Dismiss "${PO_STATUS.title}"` }));
  await waitFor(() =>
    expect(calls.some((call) => call.url === '/api/notifications/2/dismiss')).toBe(true),
  );
  expect(within(panel).queryByText('PO-31: Submitted')).not.toBeInTheDocument();
});

test('the notifications page can show only unread notifications', async () => {
  const user = userEvent.setup();
  const calls = signedIn();
  renderAt('/notifications');

  await screen.findByRole('table');
  await user.selectOptions(screen.getByLabelText('Filter'), 'unread');

  await waitFor(() =>
    expect(
      calls.some(
        (call) =>
          call.url.startsWith('/api/notifications?') && call.url.includes('unread_only=true'),
      ),
    ).toBe(true),
  );
});
