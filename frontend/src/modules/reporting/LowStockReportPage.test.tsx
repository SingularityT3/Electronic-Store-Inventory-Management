import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import LowStockReportPage from './LowStockReportPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const locations = [
  { id: 1, name: 'Chennai' },
  { id: 2, name: 'Bengaluru' },
];

const items = [
  {
    product_id: 1,
    product_name: 'Phone',
    sku: 'PHONE-1',
    variant_id: 11,
    variant_sku: 'PHONE-1-BLK',
    variant_attributes: { color: 'Black' },
    location_id: 1,
    location_name: 'Chennai',
    quantity: 3,
    reorder_threshold: 5,
    reorder_to_level: 12,
    suggested_quantity: 9,
  },
  {
    product_id: 2,
    product_name: 'Laptop',
    sku: 'LAPTOP-1',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 2,
    location_name: 'Bengaluru',
    quantity: 4,
    reorder_threshold: 4,
    reorder_to_level: 8,
    suggested_quantity: 4,
  },
  {
    product_id: 3,
    product_name: 'Headphones',
    sku: 'HEADPHONE-1',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 1,
    location_name: 'Chennai',
    quantity: 5,
    reorder_threshold: 5,
    reorder_to_level: 5,
    suggested_quantity: 0,
  },
];

function renderReport() {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url);
      const body =
        url === '/api/stock/locations'
          ? locations
          : url.endsWith('?location_id=1')
            ? items.slice(0, 1)
            : items;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => body,
      });
    }),
  );
  render(
    <MemoryRouter>
      <LowStockReportPage />
    </MemoryRouter>,
  );
  return calls;
}

test('low-stock report filters locations and links a prefilled PO', async () => {
  const calls = renderReport();
  const user = userEvent.setup();
  const table = await screen.findByRole('table', { name: 'Low-stock and reorder report' });

  expect(within(table).getByText('PHONE-1-BLK — color: Black')).toBeInTheDocument();
  expect(within(table).getByText('9')).toBeInTheDocument();
  expect(within(table).getByText('Laptop (LAPTOP-1)')).toBeInTheDocument();
  expect(within(table).getByText('No reorder needed')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Create PO for PHONE-1' })).toHaveAttribute(
    'href',
    '/purchase-orders?product_id=1&location_id=1&quantity=9&product_name=Phone&sku=PHONE-1&variant_id=11&variant_sku=PHONE-1-BLK',
  );

  await user.selectOptions(screen.getByLabelText('Location'), '1');
  await waitFor(() => {
    expect(calls).toContain('/api/reporting/reorder?location_id=1');
    expect(within(table).queryByText('LAPTOP-1')).not.toBeInTheDocument();
  });
});

test('shows report load errors', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: url === '/api/stock/locations',
        status: url === '/api/stock/locations' ? 200 : 500,
        json: async () =>
          url === '/api/stock/locations' ? locations : { detail: 'Could not load reorder data.' },
      }),
    ),
  );
  render(
    <MemoryRouter>
      <LowStockReportPage />
    </MemoryRouter>,
  );
  expect(await screen.findByRole('alert')).toHaveTextContent('Could not load reorder data.');
});

test('shows an empty state when no items are below threshold', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () => (url === '/api/stock/locations' ? locations : []),
      }),
    ),
  );
  render(
    <MemoryRouter>
      <LowStockReportPage />
    </MemoryRouter>,
  );

  expect(
    await screen.findByText('No products are at or below their reorder threshold.'),
  ).toBeInTheDocument();
});
