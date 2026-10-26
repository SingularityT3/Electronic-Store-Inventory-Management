import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Permission, type Role, type User } from '../auth';

const permissions: Record<Role, Permission[]> = {
  admin: ['products.manage', 'products.view'],
  manager: ['products.manage', 'products.view'],
  staff: ['products.view'],
  cashier: ['products.view'],
};

function renderProduct(path: string, role: Role) {
  const user: User = {
    id: 1,
    username: role,
    full_name: role,
    role,
    location_id: role === 'cashier' || role === 'staff' ? 1 : null,
    permissions: permissions[role],
  };
  const reply = (body: unknown, status = 200) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url === '/api/auth/me') return reply(user);
      if (url.startsWith('/api/product?page=')) {
        return reply({
          items: [
            {
              id: 1,
              name: 'Phone',
              sku: 'PH-001',
              category_id: 1,
              category_name: 'Phones',
              brand: 'Acme',
              price: '28999.00',
              description: null,
              is_active: true,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        });
      }

      return reply({ detail: 'Not found' }, 404);
    }),
  );
  render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

function renderCategories(role: Role) {
  const user: User = {
    id: 1,
    username: role,
    full_name: role,
    role,
    location_id: role === 'cashier' || role === 'staff' ? 1 : null,
    permissions: permissions[role],
  };
  const category = {
    id: 3,
    name: 'Smartphones',
    parent_id: 2,
    depth: 2,
    path: [
      { id: 1, name: 'Electronics' },
      { id: 2, name: 'Mobile Phones' },
      { id: 3, name: 'Smartphones' },
    ],
    path_label: 'Electronics > Mobile Phones > Smartphones',
    product_count: 1,
    total_product_count: 1,
  };
  const reply = (body: unknown, status = 200) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      if (url === '/api/auth/me') return reply(user);
      if (url === '/api/product/categories') {
        return reply([
          {
            ...category,
            id: 1,
            name: 'Electronics',
            parent_id: null,
            depth: 0,
            path: [{ id: 1, name: 'Electronics' }],
            path_label: 'Electronics',
            product_count: 0,
            total_product_count: 1,
          },
          {
            ...category,
            id: 2,
            name: 'Mobile Phones',
            parent_id: 1,
            depth: 1,
            path: category.path.slice(0, 2),
            path_label: 'Electronics > Mobile Phones',
            product_count: 0,
            total_product_count: 1,
          },
          category,
        ]);
      }
      if (url.startsWith('/api/product/categories/3/products')) {
        return reply({ items: [], total: 0, page: 1, page_size: 50 });
      }
      return reply({ detail: 'Not found' }, 404);
    }),
  );
  render(
    <MemoryRouter initialEntries={['/categories']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test('product list renders catalog rows', async () => {
  renderProduct('/products', 'manager');
  expect(await screen.findByText('PH-001')).toBeInTheDocument();
  expect(screen.getByText('Phone')).toBeInTheDocument();
});

test('cashier cannot open product management but can see search placeholder', async () => {
  renderProduct('/products/new', 'cashier');
  expect(await screen.findByText(/do not have permission/i)).toBeInTheDocument();
});

test('category tree shows hierarchy and staff is denied category management', async () => {
  renderCategories('manager');
  expect(await screen.findByText(/Smartphones \(1 \(1\)\)/)).toBeInTheDocument();
  renderCategories('staff');
  expect(await screen.findByText(/do not have permission/i)).toBeInTheDocument();
});

test('product filters and sort are sent with the search term', async () => {
  const user: User = {
    id: 1,
    username: 'manager',
    full_name: 'manager',
    role: 'manager',
    location_id: null,
    permissions: permissions.manager,
  };
  const reply = (body: unknown, status = 200) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  const fetchMock = vi.fn((url: string) => {
    if (url === '/api/auth/me') return reply(user);
    if (url === '/api/product/categories') {
      return reply([
        {
          id: 2,
          name: 'Mobile Phones',
          parent_id: null,
          depth: 0,
          path: [{ id: 2, name: 'Mobile Phones' }],
          path_label: 'Mobile Phones',
          product_count: 1,
          total_product_count: 1,
        },
      ]);
    }
    if (url.startsWith('/api/product?')) {
      return reply({ items: [], total: 0, page: 1, page_size: 50 });
    }
    return reply({ detail: 'Not found' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  render(
    <MemoryRouter initialEntries={['/products/search']}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
  const filters = await screen.findByRole('form', { name: 'Filter products' });
  await screen.findByRole('option', { name: 'Mobile Phones' });
  fireEvent.change(within(filters).getByLabelText('Category'), { target: { value: '2' } });
  fireEvent.change(within(filters).getByLabelText('Max price'), { target: { value: '20000' } });
  fireEvent.change(within(filters).getByLabelText('Stock'), { target: { value: 'low_stock' } });
  fireEvent.change(within(filters).getByLabelText('Sort by'), {
    target: { value: 'price-desc' },
  });
  fireEvent.click(within(filters).getByRole('button', { name: 'Apply filters' }));

  await waitFor(() =>
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/product?page=1&page_size=50&category_id=2&max_price=20000&stock_status=low_stock&sort=price&order=desc',
      expect.anything(),
    ),
  );

  fireEvent.change(within(filters).getByLabelText('Min price'), { target: { value: '30000' } });
  fireEvent.click(within(filters).getByRole('button', { name: 'Apply filters' }));
  expect(await screen.findByText('Minimum price cannot be above the maximum price.')).toBeVisible();
});
