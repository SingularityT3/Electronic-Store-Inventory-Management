import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import StockLevelsPage from './StockLevelsPage';

const LEVELS = [
  {
    product_id: 1,
    product_name: 'Test Phone',
    sku: 'PHONE-1',
    category_id: 10,
    category_name: 'Phones',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 1,
    location_name: 'Chennai',
    quantity: 50,
    total_quantity: 250,
  },
  {
    product_id: 1,
    product_name: 'Test Phone',
    sku: 'PHONE-1',
    category_id: 10,
    category_name: 'Phones',
    variant_id: 11,
    variant_sku: 'PHONE-1-BLK',
    variant_attributes: { color: 'Black' },
    location_id: 1,
    location_name: 'Chennai',
    quantity: 7,
    total_quantity: 20,
  },
  {
    product_id: 2,
    product_name: 'Test Laptop',
    sku: 'LAPTOP-1',
    category_id: 20,
    category_name: 'Laptops',
    variant_id: null,
    variant_sku: null,
    variant_attributes: null,
    location_id: 2,
    location_name: 'Bengaluru',
    quantity: 200,
    total_quantity: 200,
  },
];

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mockApi() {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve({
        ok: true,
        status: 200,
        json: async () =>
          url.includes('/stock/levels')
            ? LEVELS
            : [
                { id: 1, name: 'Chennai', type: 'store' },
                { id: 2, name: 'Bengaluru', type: 'warehouse' },
              ],
      }),
    ),
  );
}

test('shows per-location quantities and the combined total', async () => {
  mockApi();
  render(<StockLevelsPage />);
  expect(await screen.findByRole('heading', { name: 'Stock levels' })).toBeInTheDocument();
  const rows = await screen.findAllByRole('row');
  expect(rows).toHaveLength(4);
  expect(screen.getByText('250')).toBeInTheDocument();
  expect(screen.getByText('50')).toBeInTheDocument();
});

test('filters by location, category and product and shows an empty state', async () => {
  mockApi();
  const user = userEvent.setup();
  render(<StockLevelsPage />);
  await screen.findByText('Test Phone (PHONE-1-BLK)');

  await user.selectOptions(screen.getByLabelText('Location'), '2');
  expect(
    within(screen.getByRole('table')).getByRole('cell', { name: 'Test Laptop (LAPTOP-1)' }),
  ).toBeInTheDocument();
  expect(
    within(screen.getByRole('table')).queryByRole('cell', { name: 'Test Phone (PHONE-1)' }),
  ).not.toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Category'), '10');
  expect(await screen.findByText('No stock levels match these filters.')).toBeInTheDocument();

  await user.selectOptions(screen.getByLabelText('Location'), '');
  await user.selectOptions(screen.getByLabelText('Product'), '1');
  expect(
    within(screen.getByRole('table')).queryByRole('cell', { name: 'Test Laptop (LAPTOP-1)' }),
  ).not.toBeInTheDocument();
  expect(
    within(screen.getByRole('table')).getByRole('cell', { name: 'Test Phone (PHONE-1)' }),
  ).toBeInTheDocument();
});
