import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from './App';
import { AuthProvider, type Permission, type Role, type User } from './modules/auth';

// SEC-INP-3-IT-1: a product name holding markup is shown as text on every screen, never run.
const SCRIPT = '<script>alert(1)</script><img src=x onerror="window.__xss=1">';

const PRODUCT = {
  id: 2,
  name: SCRIPT,
  sku: 'XSS-1',
  category_id: 1,
  category_name: 'Phones',
  category_path: [],
  category_path_label: 'Phones',
  brand: 'Test',
  price: '100.00',
  description: SCRIPT,
  tracking_mode: 'untracked',
  is_active: true,
  variant_count: 0,
  stock: 10,
};

const PERMISSIONS: Record<'manager' | 'cashier', Permission[]> = {
  manager: ['products.view', 'products.manage', 'stock.view'],
  cashier: ['products.view', 'sales.record'],
};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (window as { __xss?: number }).__xss;
});

function signedInAs(role: 'manager' | 'cashier') {
  const user: User = {
    id: 1,
    username: role,
    full_name: `Test ${role}`,
    role: role as Role,
    location_id: role === 'cashier' ? 8 : null,
    permissions: PERMISSIONS[role],
  };
  const reply = (body: unknown, status = 200) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url === '/api/auth/me') return reply(user);
      if (url === '/api/product/categories') return reply([]);
      if (url.startsWith('/api/product?')) {
        return reply({ items: [PRODUCT], total: 1, page: 1, page_size: 50 });
      }
      if (url.startsWith('/api/sales/availability')) {
        return reply([
          {
            product_id: 2,
            product_name: SCRIPT,
            sku: 'XSS-1',
            variant_id: null,
            variant_sku: null,
            variant_attributes: null,
            location_id: 8,
            location_name: 'Store',
            available_quantity: 10,
          },
        ]);
      }
      return reply({ detail: 'Not found' }, 404);
    }),
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

function expectInert() {
  expect(document.querySelector('script')).toBeNull();
  expect(document.querySelector('img[onerror]')).toBeNull();
  expect((window as { __xss?: number }).__xss).toBeUndefined();
}

test('the product list shows a script name literally', async () => {
  signedInAs('manager');
  renderAt('/products');

  expect((await screen.findAllByText(SCRIPT, { exact: false })).length).toBeGreaterThan(0);
  expectInert();
});

test('search results show a script name literally', async () => {
  signedInAs('cashier');
  renderAt('/products/search?q=XSS');

  expect((await screen.findAllByText(SCRIPT, { exact: false })).length).toBeGreaterThan(0);
  expectInert();
});

test('the sales screen shows a script name literally in results and the cart', async () => {
  const user = userEvent.setup();
  signedInAs('cashier');
  renderAt('/sales');

  const search = await screen.findByRole('searchbox', { name: 'Find a product' });
  await user.type(search, 'XSS-1');
  await user.keyboard('{Enter}');

  expect((await screen.findAllByText(SCRIPT, { exact: false })).length).toBeGreaterThan(0);
  expect(screen.getByRole('heading', { name: 'Cart' })).toBeInTheDocument();
  expectInert();
});
