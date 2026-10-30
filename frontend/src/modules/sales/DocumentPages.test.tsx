import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider, type User } from '../auth';
import { SalesHistoryPage } from './DocumentPages';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const cashier: User = {
  id: 7,
  username: 'cashier',
  full_name: 'Ravi Kumar',
  role: 'cashier',
  location_id: 3,
  permissions: ['sales.record'],
};

function setup(user: User, items: object[] = []) {
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    const body = url.endsWith('/auth/me')
      ? user
      : {
          items,
          total: items.length,
          page: 1,
          page_size: 25,
        };
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  render(
    <MemoryRouter initialEntries={['/sales/history']}>
      <AuthProvider>
        <SalesHistoryPage />
      </AuthProvider>
    </MemoryRouter>,
  );
  return fetchMock;
}

test('sales history filters by invoice and shows the empty state', async () => {
  const fetchMock = setup(cashier);
  const user = userEvent.setup();
  expect(await screen.findByText('No sales found')).toBeInTheDocument();
  await user.type(screen.getByLabelText('Invoice number'), 'INV-0007');
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('invoice=INV-0007'))).toBe(
      true,
    ),
  );
  expect(screen.queryByLabelText('Location')).not.toBeInTheDocument();
});

test('Manager sees the location filter in sales history', async () => {
  const manager: User = {
    ...cashier,
    role: 'manager',
    permissions: ['sales.record', 'locations.manage'],
  };
  const fetchMock = vi.fn(async (input: string | URL | Request) => {
    const url = String(input);
    const body = url.endsWith('/auth/me')
      ? manager
      : url.endsWith('/stock/locations/all')
        ? [{ id: 3, name: 'Main Store' }]
        : { items: [], total: 0, page: 1, page_size: 25 };
    return { ok: true, status: 200, json: async () => body } as Response;
  });
  vi.stubGlobal('fetch', fetchMock);
  render(
    <MemoryRouter initialEntries={['/sales/history']}>
      <AuthProvider>
        <SalesHistoryPage />
      </AuthProvider>
    </MemoryRouter>,
  );
  expect(await screen.findByRole('option', { name: 'Main Store' })).toBeInTheDocument();
});
