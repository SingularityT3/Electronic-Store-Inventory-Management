import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Role, type User } from '../auth';

const HISTORY = [
  {
    id: 1,
    supplier_id: 3,
    supplier_name: 'Northwind Supply',
    product_id: 7,
    product_name: 'Phone',
    variant_id: null,
    sku: 'PHONE-7',
    unit_price: '25000.00',
    recorded_at: '2026-10-27T09:00:00Z',
    receipt_line_id: 31,
  },
  {
    id: 2,
    supplier_id: 4,
    supplier_name: 'Contoso Wholesale',
    product_id: 7,
    product_name: 'Phone',
    variant_id: null,
    sku: 'PHONE-7',
    unit_price: '24000.00',
    recorded_at: '2026-10-27T10:00:00Z',
    receipt_line_id: 32,
  },
];

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
    location_id: role === 'staff' || role === 'cashier' ? 1 : null,
    permissions:
      role === 'admin' || role === 'manager' ? ['suppliers.manage', 'products.view'] : [],
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body });
}

test('Manager can filter immutable receipt price history by supplier and product', async () => {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url);
      if (url === '/api/auth/me') return reply(200, userFor('manager'));
      if (url === '/api/purchasing/suppliers') {
        return reply(200, [
          { id: 3, name: 'Northwind Supply' },
          { id: 4, name: 'Contoso Wholesale' },
        ]);
      }
      if (url === '/api/product?page=1&page_size=50') {
        return reply(200, {
          items: [
            {
              id: 7,
              name: 'Phone',
              sku: 'PHONE-7',
              category_id: 1,
              category_name: 'Phones',
              category_path: [],
              category_path_label: 'Phones',
              brand: 'Test',
              price: '30000.00',
              description: null,
              tracking_mode: 'untracked',
              is_active: true,
              variant_count: 0,
              stock: 0,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        });
      }
      if (url.startsWith('/api/purchasing/suppliers/price-history')) {
        const query = url.split('?')[1];
        const params = new URLSearchParams(query);
        const filtered = HISTORY.filter(
          (entry) =>
            (!params.has('supplier_id') ||
              entry.supplier_id === Number(params.get('supplier_id'))) &&
            (!params.has('product_id') || entry.product_id === Number(params.get('product_id'))),
        );
        return reply(200, filtered);
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  render(
    <MemoryRouter
      initialEntries={['/suppliers/price-history']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  const user = userEvent.setup();
  expect(
    await screen.findByRole('heading', { name: 'Supplier price history' }),
  ).toBeInTheDocument();
  const table = screen.getByRole('table', { name: 'Supplier price history' });
  expect(within(table).getByText('25000.00')).toBeInTheDocument();
  expect(within(table).getByText('24000.00')).toBeInTheDocument();
  expect(within(table).getByText('Northwind Supply')).toBeInTheDocument();
  expect(within(table).getByText('Contoso Wholesale')).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Supplier'), '3');
  await user.selectOptions(screen.getByLabelText('Product'), '7');

  expect(await within(table).findByText('25000.00')).toBeInTheDocument();
  expect(within(table).queryByText('24000.00')).not.toBeInTheDocument();
  expect(calls).toContain('/api/purchasing/suppliers/price-history?supplier_id=3');
  expect(calls).toContain('/api/purchasing/suppliers/price-history?supplier_id=3&product_id=7');
});

test.each(['staff', 'cashier'] as const)('%s cannot view supplier price history', async (role) => {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url);
      if (url === '/api/auth/me') return reply(200, userFor(role));
      return reply(404, { detail: 'Not found' });
    }),
  );
  render(
    <MemoryRouter
      initialEntries={['/suppliers/price-history']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(calls).not.toContain('/api/purchasing/suppliers/price-history');
});
