import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Role, type User } from '../auth';

const SUPPLIER = {
  id: 4,
  name: 'Acme Supply',
  contact_name: 'Morgan Lee',
  email: 'morgan@example.com',
  phone: null,
  address: null,
  is_active: true,
};

const PRODUCT = {
  id: 12,
  name: 'Test Phone',
  sku: 'PHONE-12',
  category_id: 2,
  category_name: 'Phones',
  category_path: [],
  category_path_label: 'Phones',
  brand: 'Acme',
  price: '100.00',
  description: null,
  is_active: true,
};

const CATALOG_ENTRY = {
  id: 9,
  supplier_id: SUPPLIER.id,
  product_id: PRODUCT.id,
  variant_id: null,
  supplier_sku: 'ACME-12',
  supplier_price: '82.50',
  product_name: PRODUCT.name,
  product_sku: PRODUCT.sku,
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
    location_id: role === 'staff' || role === 'cashier' ? 1 : null,
    permissions:
      role === 'admin' || role === 'manager' ? ['suppliers.manage', 'products.view'] : [],
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({ ok: status < 400, status, json: async () => body });
}

function renderPage(role: Role = 'manager') {
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      if (url === '/api/auth/me') return reply(200, userFor(role));
      if (url === '/api/purchasing/suppliers' && (!init?.method || init.method === 'GET')) {
        return reply(200, [SUPPLIER]);
      }
      if (url === '/api/product?page=1&page_size=50') {
        return reply(200, { items: [PRODUCT], total: 1, page: 1, page_size: 50 });
      }
      if (url === `/api/product/${PRODUCT.id}/variants`) return reply(200, []);
      if (
        url === `/api/purchasing/suppliers/${SUPPLIER.id}/products` &&
        (!init?.method || init.method === 'GET')
      ) {
        return reply(200, [CATALOG_ENTRY]);
      }
      if (url === '/api/purchasing/suppliers' && init?.method === 'POST') {
        return reply(422, { detail: 'Invalid email format' });
      }
      if (url === `/api/purchasing/suppliers/${SUPPLIER.id}/products` && init?.method === 'POST') {
        return reply(201, CATALOG_ENTRY);
      }
      if (
        url === `/api/purchasing/suppliers/${SUPPLIER.id}/products/9` &&
        init?.method === 'PATCH'
      ) {
        return reply(200, { ...CATALOG_ENTRY, supplier_price: '90.00' });
      }
      if (
        url === `/api/purchasing/suppliers/${SUPPLIER.id}/products/9` &&
        init?.method === 'DELETE'
      ) {
        return reply(204, undefined);
      }
      if (url === `/api/purchasing/suppliers/${SUPPLIER.id}` && init?.method === 'PATCH') {
        return reply(200, { ...SUPPLIER, name: 'Acme Electronics' });
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  render(
    <MemoryRouter
      initialEntries={['/suppliers']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
  return calls;
}

test('renders supplier management at the guarded route and handles supplier email errors', async () => {
  const user = userEvent.setup();
  const calls = renderPage();

  expect(await screen.findByRole('heading', { name: 'Suppliers' })).toBeInTheDocument();
  expect(screen.getByText('Acme Supply')).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Add supplier' }));
  await user.type(screen.getByLabelText('Name'), 'Invalid Supplier');
  await user.type(screen.getByLabelText('Email'), 'bad@domain');
  await user.click(screen.getByRole('button', { name: 'Create supplier' }));

  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid email format');
  const createCall = calls.find(
    (call) => call.url === '/api/purchasing/suppliers' && call.init?.method === 'POST',
  );
  expect(JSON.parse(String(createCall?.init?.body))).toMatchObject({
    name: 'Invalid Supplier',
    email: 'bad@domain',
  });
});

test('loads supplier catalog and submits product association changes', async () => {
  const user = userEvent.setup();
  const calls = renderPage();

  await user.click(await screen.findByRole('button', { name: 'Acme Supply' }));
  expect(await screen.findByRole('option', { name: 'Test Phone (PHONE-12)' })).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Product or variant'), '12:');
  await user.type(screen.getByLabelText('Supplier SKU'), 'NEW-SKU');
  await user.type(screen.getByLabelText('Supplier price'), '82.50');
  await user.click(screen.getByRole('button', { name: 'Add catalog item' }));
  const addCall = calls.find(
    (call) =>
      call.url === `/api/purchasing/suppliers/${SUPPLIER.id}/products` &&
      call.init?.method === 'POST',
  );
  expect(JSON.parse(String(addCall?.init?.body))).toEqual({
    product_id: PRODUCT.id,
    variant_id: null,
    supplier_sku: 'NEW-SKU',
    supplier_price: '82.5',
  });

  await user.click(screen.getByRole('button', { name: 'Edit' }));
  await user.clear(screen.getByLabelText('Supplier price'));
  await user.type(screen.getByLabelText('Supplier price'), '90.00');
  await user.click(screen.getByRole('button', { name: 'Save catalog item' }));
  expect(
    calls.some(
      (call) =>
        call.url === `/api/purchasing/suppliers/${SUPPLIER.id}/products/9` &&
        call.init?.method === 'PATCH',
    ),
  ).toBe(true);

  await user.click(screen.getByRole('button', { name: 'Remove' }));
  expect(
    calls.some(
      (call) =>
        call.url === `/api/purchasing/suppliers/${SUPPLIER.id}/products/9` &&
        call.init?.method === 'DELETE',
    ),
  ).toBe(true);
  expect(screen.getByRole('button', { name: 'Add catalog item' })).toBeInTheDocument();
});

test.each(['staff', 'cashier'] as const)(
  '%s is denied access to supplier management',
  async (role) => {
    const calls = renderPage(role);

    expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
    expect(calls.map((call) => call.url)).not.toContain('/api/purchasing/suppliers');
  },
);
