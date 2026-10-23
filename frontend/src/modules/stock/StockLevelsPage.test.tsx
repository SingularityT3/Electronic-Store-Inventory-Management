import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AuthProvider, type Permission } from '../auth';
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

function mockApi(
  permissions: Permission[] = ['stock.view'],
  adjustStatus = 201,
  adjustBody: unknown = {},
) {
  const adjustCalls: RequestInit[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      let status = 200;
      let body: unknown;
      if (url === '/api/auth/me') {
        body = {
          id: 1,
          username: 'u',
          full_name: 'U',
          role: 'manager',
          location_id: null,
          permissions,
        };
      } else if (url === '/api/stock/adjustments') {
        adjustCalls.push(init ?? {});
        status = adjustStatus;
        body = adjustBody;
      } else if (url.includes('/stock/levels')) {
        body = LEVELS;
      } else {
        body = [
          { id: 1, name: 'Chennai', type: 'store' },
          { id: 2, name: 'Bengaluru', type: 'warehouse' },
        ];
      }
      return Promise.resolve({ ok: status < 400, status, json: async () => body });
    }),
  );
  return adjustCalls;
}

function renderPage() {
  render(
    <AuthProvider>
      <StockLevelsPage />
    </AuthProvider>,
  );
}

test('shows per-location quantities and the combined total', async () => {
  mockApi();
  renderPage();
  expect(await screen.findByRole('heading', { name: 'Stock levels' })).toBeInTheDocument();
  const rows = await screen.findAllByRole('row');
  expect(rows).toHaveLength(4);
  expect(screen.getByText('250')).toBeInTheDocument();
  expect(screen.getByText('50')).toBeInTheDocument();
});

test('filters by location, category and product and shows an empty state', async () => {
  mockApi();
  const user = userEvent.setup();
  renderPage();
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

test('hides the Adjust action from users without stock.adjust', async () => {
  mockApi(['stock.view']);
  renderPage();
  await screen.findByRole('cell', { name: 'Test Laptop (LAPTOP-1)' });
  expect(screen.queryByRole('button', { name: /^Adjust/ })).not.toBeInTheDocument();
});

test('submits a signed adjustment with its reason', async () => {
  const user = userEvent.setup();
  const calls = mockApi(['stock.view', 'stock.adjust']);
  renderPage();
  await user.click(
    await screen.findByRole('button', { name: 'Adjust Test Laptop (LAPTOP-1) at Bengaluru' }),
  );
  await user.type(screen.getByLabelText('Quantity change'), '-5');
  await user.selectOptions(screen.getByLabelText('Reason type'), 'damage');
  await user.type(screen.getByLabelText('Reason'), 'Damaged');
  await user.click(screen.getByRole('button', { name: 'Adjust stock' }));

  expect(await screen.findByRole('status')).toHaveTextContent('Stock adjusted');
  expect(JSON.parse(String(calls[0].body))).toEqual({
    product_id: 2,
    variant_id: null,
    location_id: 2,
    quantity_change: -5,
    reason_code: 'damage',
    reason: 'Damaged',
  });
});

test('blocks a blank reason without calling the API', async () => {
  const user = userEvent.setup();
  const calls = mockApi(['stock.view', 'stock.adjust']);
  renderPage();
  await user.click(
    await screen.findByRole('button', { name: 'Adjust Test Laptop (LAPTOP-1) at Bengaluru' }),
  );
  await user.type(screen.getByLabelText('Quantity change'), '-1');
  await user.click(screen.getByRole('button', { name: 'Adjust stock' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Reason is required for stock adjustment',
  );
  expect(calls).toHaveLength(0);
});

test('shows the API error when the adjustment would go negative', async () => {
  const user = userEvent.setup();
  mockApi(['stock.view', 'stock.adjust'], 409, {
    detail: 'Adjustment would result in negative stock',
  });
  renderPage();
  await user.click(
    await screen.findByRole('button', { name: 'Adjust Test Laptop (LAPTOP-1) at Bengaluru' }),
  );
  await user.type(screen.getByLabelText('Quantity change'), '-500');
  await user.type(screen.getByLabelText('Reason'), 'Lost');
  await user.click(screen.getByRole('button', { name: 'Adjust stock' }));
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'Adjustment would result in negative stock',
  );
});
