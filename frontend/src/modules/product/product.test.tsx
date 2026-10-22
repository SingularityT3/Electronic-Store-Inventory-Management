import { render, screen } from '@testing-library/react';
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

test('product list renders catalog rows', async () => {
  renderProduct('/products', 'manager');
  expect(await screen.findByText('PH-001')).toBeInTheDocument();
  expect(screen.getByText('Phone')).toBeInTheDocument();
});

test('cashier cannot open product management but can see search placeholder', async () => {
  renderProduct('/products/new', 'cashier');
  expect(await screen.findByText(/do not have permission/i)).toBeInTheDocument();
});
