import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import StockValuationPage from './StockValuationPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const locations = [
  { id: 1, name: 'Chennai' },
  { id: 2, name: 'Bengaluru' },
];

const allLocationsReport = {
  items: [
    {
      product_id: 1,
      product_name: 'Phone',
      sku: 'PHONE-1',
      variant_id: 2,
      variant_sku: 'PHONE-1-BLK',
      variant_attributes: { color: 'Black' },
      location_id: 1,
      location_name: 'Chennai',
      quantity: 3,
      unit_cost: '100.0000',
      value: '300.0000',
      cost_not_set: false,
    },
    {
      product_id: 1,
      product_name: 'Phone',
      sku: 'PHONE-1',
      variant_id: null,
      variant_sku: null,
      variant_attributes: null,
      location_id: 2,
      location_name: 'Bengaluru',
      quantity: 2,
      unit_cost: '0',
      value: '0',
      cost_not_set: true,
    },
  ],
  total_value: '300',
};

function mockApi(report = allLocationsReport) {
  const calls: string[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) => {
      calls.push(url);
      const body =
        url === '/api/stock/locations'
          ? locations
          : url.endsWith('?location_id=1')
            ? {
                items: allLocationsReport.items.slice(0, 1),
                total_value: '300',
              }
            : report;
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => body,
      });
    }),
  );
  return calls;
}

function renderPage() {
  render(
    <MemoryRouter>
      <StockValuationPage />
    </MemoryRouter>,
  );
}

test('shows valuation details and refreshes the report when filtering by location', async () => {
  const calls = mockApi();
  const user = userEvent.setup();
  renderPage();

  expect(screen.getByText('Loading stock valuation…')).toBeInTheDocument();
  const table = await screen.findByRole('table', { name: 'Stock valuation' });
  expect(within(table).getAllByText('Phone (PHONE-1)')).toHaveLength(2);
  expect(within(table).getByText('PHONE-1-BLK — color: Black')).toBeInTheDocument();
  expect(within(table).getByText('Cost not set')).toBeInTheDocument();
  expect(screen.getByText('Total inventory value:')).toHaveTextContent('₹300.00');

  await user.selectOptions(screen.getByLabelText('Location'), '1');
  await waitFor(() => {
    expect(calls).toContain('/api/reporting/valuation?location_id=1');
    expect(within(table).queryByText('Bengaluru')).not.toBeInTheDocument();
  });
  expect(calls).toContain('/api/reporting/valuation?location_id=1');
  expect(calls).toContain('/api/reporting/valuation');
});

test('shows an empty state when the selected location has no stock', async () => {
  mockApi({ items: [], total_value: '0' });
  renderPage();

  expect(await screen.findByText('No stock valuation data for this location.')).toBeInTheDocument();
  expect(screen.getByText('Total inventory value:')).toHaveTextContent('₹0.00');
});

test('shows report load errors', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: url === '/api/stock/locations',
        status: url === '/api/stock/locations' ? 200 : 500,
        json: async () =>
          url === '/api/stock/locations' ? locations : { detail: 'Report unavailable.' },
      }),
    ),
  );
  renderPage();

  expect(await screen.findByRole('alert')).toHaveTextContent('Report unavailable.');
});
