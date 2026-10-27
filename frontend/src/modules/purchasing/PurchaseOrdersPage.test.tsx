import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Role, type User } from '../auth';
import type { PurchaseOrder } from './api';

const SUPPLIER = {
  id: 5,
  name: 'Northwind Supply',
  contact_name: null,
  email: 'orders@northwind.example',
  phone: null,
  address: null,
  is_active: true,
};

const CATALOG = {
  id: 8,
  supplier_id: SUPPLIER.id,
  product_id: 20,
  variant_id: null,
  supplier_sku: 'NW-PHONE',
  supplier_price: '80.00',
  product_name: 'Phone',
  product_sku: 'PHONE-20',
};

const ORDER: PurchaseOrder = {
  id: 31,
  po_number: 'PO-20261023-1234ABCD',
  supplier_id: SUPPLIER.id,
  supplier_name: SUPPLIER.name,
  location_id: 2,
  status: 'draft',
  created_by: 1,
  notes: null,
  expected_delivery_date: '2026-11-12',
  submitted_at: null,
  created_at: '2026-10-23T10:00:00Z',
  lines: [
    {
      id: 41,
      product_id: CATALOG.product_id,
      product_name: CATALOG.product_name,
      sku: CATALOG.product_sku,
      variant_id: null,
      tracking_mode: 'untracked',
      quantity_ordered: 2,
      quantity_received: 0,
      quantity_outstanding: 2,
      unit_price: '75.50',
      line_total: '151.00',
    },
  ],
  total: '151.00',
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function userFor(role: Role): User {
  return {
    id: 1,
    username: role,
    full_name: role,
    role,
    location_id: role === 'staff' || role === 'cashier' ? 2 : null,
    permissions:
      role === 'admin' || role === 'manager'
        ? ['purchase_orders.manage', 'suppliers.manage', 'stock.view']
        : [],
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body });
}

function renderPurchaseOrders(role: Role = 'manager') {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === '/api/auth/me') return reply(200, userFor(role));
      if (url === '/api/purchasing/purchase-orders') {
        if (init?.method === 'POST') return reply(201, ORDER);
        return reply(200, []);
      }
      if (url === `/api/purchasing/purchase-orders/${ORDER.id}/submit`) {
        return reply(200, { ...ORDER, status: 'submitted', submitted_at: '2026-10-23T10:05:00Z' });
      }
      if (url === '/api/purchasing/suppliers?active_only=true') return reply(200, [SUPPLIER]);
      if (url === '/api/stock/locations') {
        return reply(200, [{ id: 2, name: 'Central Warehouse', type: 'warehouse' }]);
      }
      if (url === `/api/purchasing/suppliers/${SUPPLIER.id}/products`) {
        return reply(200, [CATALOG]);
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  render(
    <MemoryRouter
      initialEntries={['/purchase-orders']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
  return calls;
}

test('creates a draft from supplier catalog prices, recalculates totals and submits it', async () => {
  const user = userEvent.setup();
  const calls = renderPurchaseOrders();

  expect(await screen.findByRole('heading', { name: 'Purchase orders' })).toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Supplier'), String(SUPPLIER.id));
  await user.selectOptions(screen.getByLabelText('Receiving location'), '2');
  await user.type(screen.getByLabelText('Expected delivery date'), '2026-11-12');
  await user.selectOptions(screen.getByLabelText('Supplier catalog item'), String(CATALOG.id));
  await user.click(screen.getByRole('button', { name: 'Add line' }));
  expect(screen.getByLabelText('Unit price PHONE-20')).toHaveValue(80);
  await user.clear(screen.getByLabelText('Quantity PHONE-20'));
  await user.type(screen.getByLabelText('Quantity PHONE-20'), '2');
  await user.clear(screen.getByLabelText('Unit price PHONE-20'));
  await user.type(screen.getByLabelText('Unit price PHONE-20'), '75.50');
  expect(screen.getByText('151.00', { selector: 'strong' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Create draft' }));

  const createCall = calls.find(
    (call) => call.url === '/api/purchasing/purchase-orders' && call.init?.method === 'POST',
  );
  expect(JSON.parse(String(createCall?.init?.body))).toEqual({
    supplier_id: SUPPLIER.id,
    location_id: 2,
    expected_delivery_date: '2026-11-12',
    notes: null,
    lines: [
      {
        product_id: CATALOG.product_id,
        variant_id: null,
        quantity_ordered: 2,
        unit_price: '75.50',
      },
    ],
  });
  await user.click(await screen.findByRole('button', { name: 'Submit purchase order' }));
  expect(
    calls.some(
      (call) =>
        call.url === `/api/purchasing/purchase-orders/${ORDER.id}/submit` &&
        call.init?.method === 'POST',
    ),
  ).toBe(true);
  expect(await screen.findByText('Purchase order submitted.')).toBeInTheDocument();
});

test.each(['staff', 'cashier'] as const)(
  '%s cannot open the purchase order management route',
  async (role) => {
    const calls = renderPurchaseOrders(role);

    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(calls.map((call) => call.url)).not.toContain('/api/purchasing/purchase-orders');
  },
);
