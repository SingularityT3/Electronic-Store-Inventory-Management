import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { AuthProvider } from '../auth';
import SalesAvailabilityPage from './AvailabilityPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

test('cashier sees availability from the assigned location without requesting all locations', async () => {
  const cashier = {
    id: 1,
    username: 'cashier',
    full_name: 'Cashier User',
    role: 'cashier' as const,
    location_id: 8,
    permissions: ['sales.record', 'products.view'] as const,
  };
  const fetchMock = vi.fn((url: string) =>
    Promise.resolve({
      ok: true,
      status: 200,
      json: async () =>
        url.endsWith('/auth/me')
          ? cashier
          : [
              {
                product_id: 2,
                product_name: 'Phone',
                sku: 'PHONE-1',
                variant_id: null,
                variant_sku: null,
                variant_attributes: null,
                location_id: 8,
                location_name: 'Assigned Store',
                available_quantity: 70,
              },
            ],
    }),
  );
  vi.stubGlobal('fetch', fetchMock);

  render(
    <MemoryRouter initialEntries={['/sales']}>
      <AuthProvider>
        <SalesAvailabilityPage />
      </AuthProvider>
    </MemoryRouter>,
  );

  expect(await screen.findByRole('heading', { name: 'Sales availability' })).toBeInTheDocument();
  expect(await screen.findByRole('cell', { name: 'Assigned Store' })).toBeInTheDocument();
  expect(screen.getByText('70')).toBeInTheDocument();
  const requestedUrls = fetchMock.mock.calls.map(([url]) => url);
  expect(requestedUrls).toContain('/api/sales/availability?location_id=8');
  expect(requestedUrls).not.toContain('/api/stock/locations');
});
