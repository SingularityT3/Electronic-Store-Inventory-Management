import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider } from '../auth';
import PosPage from './PosPage';

const cashier = {
  id: 1,
  username: 'cashier',
  full_name: 'Cashier User',
  role: 'cashier' as const,
  location_id: 8,
  permissions: ['sales.record', 'products.view'] as const,
};

const product = {
  id: 2,
  name: 'Test Phone',
  sku: 'PHONE-1',
  category_id: 1,
  category_name: 'Phones',
  category_path: [],
  category_path_label: 'Phones',
  brand: 'Test',
  price: '100.00',
  description: null,
  tracking_mode: 'untracked' as const,
  is_active: true,
  variant_count: 0,
  stock: 10,
};

const availability = {
  product_id: 2,
  product_name: 'Test Phone',
  sku: 'PHONE-1',
  variant_id: null,
  variant_sku: null,
  variant_attributes: null,
  location_id: 8,
  location_name: 'Assigned Store',
  available_quantity: 10,
  unit_price: '100.00',
};

function mockApi() {
  const calls: [string, RequestInit | undefined][] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push([url, init]);
      let body: unknown = {};
      if (url === '/api/auth/me') body = cashier;
      else if (url.startsWith('/api/product?'))
        body = { items: [product], total: 1, page: 1, page_size: 20 };
      else if (url.startsWith('/api/sales/availability')) body = [availability];
      else if (url === '/api/sales') {
        body = {
          id: 5,
          location_id: 8,
          cashier_id: 1,
          sold_at: '2026-11-01T10:00:00Z',
          subtotal: '100.00',
          discount_total: '0.00',
          tax_total: '18.00',
          total: '118.00',
          customer_name: null,
          lines: [],
          payments: [],
          invoice: {
            invoice_number: 1,
            invoice_label: 'INV-1',
            issued_at: '2026-11-01T10:00:00Z',
            total: '118.00',
            content: { kind: 'invoice', store_name: 'ESIMS', location_name: 'Store', lines: [] },
          },
        };
      }
      return Promise.resolve({ ok: true, status: 200, json: async () => body });
    }),
  );
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function renderPage() {
  render(
    <AuthProvider>
      <PosPage />
    </AuthProvider>,
  );
}

test('scanner-style Enter adds the only matching product and refocuses search', async () => {
  mockApi();
  const user = userEvent.setup();
  renderPage();
  const search = await screen.findByRole('searchbox', { name: 'Find a product' });
  expect(search).toHaveFocus();
  await user.type(search, 'PHONE-1');
  await user.keyboard('{Enter}');
  expect(await screen.findByText('Test Phone')).toBeInTheDocument();
  expect(screen.getByLabelText('Find a product')).toHaveFocus();
  expect(screen.getByRole('heading', { name: 'Cart' })).toBeInTheDocument();
  expect(screen.getByLabelText('Quantity')).toHaveValue(1);
});

test('Alt shortcuts focus search and complete a sale', async () => {
  const calls = mockApi();
  const user = userEvent.setup();
  renderPage();
  const search = await screen.findByRole('searchbox', { name: 'Find a product' });
  await user.type(search, 'PHONE-1');
  await user.keyboard('{Enter}');
  await screen.findByLabelText('Quantity');
  await user.keyboard('{Alt>}s{/Alt}');
  expect(search).toHaveFocus();
  await user.keyboard('{Alt>}{Enter}{/Alt}');
  expect(await screen.findByRole('heading', { name: 'Sale recorded' })).toBeInTheDocument();
  expect(calls.some(([url]) => url === '/api/sales')).toBe(true);
});
