import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { AuthProvider, type Role, type User } from '../auth';
import StockTransferPage from './StockTransferPage';

const LOCATIONS = [
  { id: 1, name: 'Chennai', type: 'store' },
  { id: 2, name: 'Bengaluru', type: 'warehouse' },
];

const LEVELS = [
  {
    product_id: 10,
    product_name: 'Test Phone',
    sku: 'PHONE-1',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 1,
    location_name: 'Chennai',
    quantity: 5,
  },
  {
    product_id: 10,
    product_name: 'Test Phone',
    sku: 'PHONE-1',
    variant_id: 11,
    variant_sku: 'PHONE-1-BLK',
    variant_attributes: { color: 'Black' },
    location_id: 1,
    location_name: 'Chennai',
    quantity: 3,
  },
  {
    product_id: 12,
    product_name: 'Test Laptop',
    sku: 'LAPTOP-1',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 2,
    location_name: 'Bengaluru',
    quantity: 8,
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function makeUser(role: Role): User {
  return {
    id: 1,
    username: `${role}_user`,
    full_name: `${role} user`,
    role,
    location_id: role === 'staff' ? 1 : null,
    permissions: role === 'cashier' ? ['sales.record'] : ['stock.view', 'stock.transfer'],
  };
}

function reply(status: number, body: unknown) {
  return Promise.resolve({
    ok: status < 400,
    status,
    json: async () => body,
  });
}

function mockFetch(role: Role, transferStatus = 201, transferBody: unknown = { id: 1 }) {
  const transferCalls: { url: string; init?: RequestInit }[] = [];
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url === '/api/auth/me') return reply(200, makeUser(role));
    if (url === '/api/stock/levels') return reply(200, LEVELS);
    if (url === '/api/stock/transfers/locations') return reply(200, LOCATIONS);
    if (url === '/api/stock/transfers' && init?.method === 'POST') {
      transferCalls.push({ url, init });
      return reply(transferStatus, transferBody);
    }
    return reply(404, { detail: 'Not found' });
  });
  vi.stubGlobal('fetch', fetchMock);
  return { fetchMock, transferCalls };
}

function renderStandalone() {
  render(
    <MemoryRouter>
      <AuthProvider>
        <StockTransferPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

test('the Stock Transfer navigation route renders the guarded transfer form', async () => {
  mockFetch('manager');
  render(
    <MemoryRouter
      initialEntries={['/stock/transfer']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Stock transfer' })).toBeInTheDocument();
  expect(screen.getByRole('form', { name: 'Stock transfer' })).toBeInTheDocument();
});

test('Cashier is denied the transfer route by the existing permission guard', async () => {
  const { fetchMock } = mockFetch('cashier');
  render(
    <MemoryRouter
      initialEntries={['/stock/transfer']}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Access denied' })).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent(
    'You do not have permission to view stock transfers.',
  );
  expect(fetchMock.mock.calls.map(([url]) => url)).not.toContain('/api/stock/transfers/locations');
});

test('selects a variant and submits a transfer using the existing endpoint', async () => {
  const user = userEvent.setup();
  const { transferCalls } = mockFetch('manager');
  renderStandalone();

  await screen.findByRole('heading', { name: 'Stock transfer' });
  await within(screen.getByLabelText('Source location')).findByRole('option', {
    name: 'Chennai',
  });
  await user.selectOptions(screen.getByLabelText('Source location'), '1');
  const product = screen.getByLabelText('Product or variant');
  expect(
    within(product).getByRole('option', { name: 'Test Phone (PHONE-1-BLK)' }),
  ).toBeInTheDocument();
  await user.selectOptions(product, '10:11');
  await user.selectOptions(screen.getByLabelText('Destination location'), '2');
  await user.type(screen.getByLabelText('Quantity'), '2');
  await user.click(screen.getByRole('button', { name: 'Transfer stock' }));

  expect(transferCalls).toHaveLength(1);
  expect(transferCalls[0].url).toBe('/api/stock/transfers');
  expect(JSON.parse(String(transferCalls[0].init?.body))).toEqual({
    product_id: 10,
    variant_id: 11,
    from_location_id: 1,
    to_location_id: 2,
    quantity: 2,
  });
  expect(await screen.findByRole('status')).toHaveTextContent(
    'Stock transfer completed successfully.',
  );
});

test('prevents selecting the source as destination and blocks invalid quantities', async () => {
  const user = userEvent.setup();
  const { transferCalls } = mockFetch('manager');
  renderStandalone();

  await screen.findByRole('heading', { name: 'Stock transfer' });
  await within(screen.getByLabelText('Source location')).findByRole('option', {
    name: 'Chennai',
  });
  await user.selectOptions(screen.getByLabelText('Source location'), '1');
  const destination = screen.getByLabelText('Destination location');
  expect(within(destination).queryByRole('option', { name: 'Chennai' })).not.toBeInTheDocument();
  await user.selectOptions(screen.getByLabelText('Product or variant'), '10:');
  await user.selectOptions(destination, '2');
  await user.type(screen.getByLabelText('Quantity'), '0');
  expect(screen.getByRole('button', { name: 'Transfer stock' })).toBeDisabled();
  expect(transferCalls).toHaveLength(0);
});

test('shows a readable API error when the transfer is rejected', async () => {
  const user = userEvent.setup();
  mockFetch('manager', 409, { detail: 'Insufficient stock at the source location.' });
  renderStandalone();

  await screen.findByRole('heading', { name: 'Stock transfer' });
  await within(screen.getByLabelText('Source location')).findByRole('option', {
    name: 'Chennai',
  });
  await user.selectOptions(screen.getByLabelText('Source location'), '1');
  await user.selectOptions(screen.getByLabelText('Product or variant'), '10:');
  await user.selectOptions(screen.getByLabelText('Destination location'), '2');
  await user.type(screen.getByLabelText('Quantity'), '9');
  await user.click(screen.getByRole('button', { name: 'Transfer stock' }));

  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Insufficient stock at the source location.',
  );
});

test('limits Staff to their assigned source while retaining other destination choices', async () => {
  mockFetch('staff');
  renderStandalone();

  await screen.findByRole('heading', { name: 'Stock transfer' });
  const source = screen.getByLabelText('Source location');
  expect(within(source).getAllByRole('option')).toHaveLength(2);
  expect(within(source).getByRole('option', { name: 'Chennai' })).toBeInTheDocument();
  expect(within(source).queryByRole('option', { name: 'Bengaluru' })).not.toBeInTheDocument();
  expect(screen.getByLabelText('Source location')).toHaveValue('1');
  expect(screen.getByLabelText('Destination location')).toHaveTextContent('Bengaluru');
});
