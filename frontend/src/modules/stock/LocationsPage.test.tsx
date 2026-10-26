import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import LocationsPage from './LocationsPage';

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function mockApi() {
  let locations = [
    { id: 1, name: 'Store-Chennai-01', type: 'store', address: null, is_active: true },
    { id: 2, name: 'Old Depot', type: 'warehouse', address: 'Hosur', is_active: false },
  ];
  const calls: { url: string; init?: RequestInit }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string, init?: RequestInit) => {
      calls.push({ url, init });
      const reply = (status: number, body: unknown) =>
        Promise.resolve({ ok: status < 400, status, json: async () => body });
      if (url === '/api/stock/locations/all') return reply(200, locations);
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      if (url === '/api/stock/locations' && init?.method === 'POST') {
        if (body.name === 'Store-Chennai-01') {
          return reply(409, { detail: 'A location with this name already exists.' });
        }
        locations = [...locations, { ...body, id: 3 }];
        return reply(201, locations.at(-1));
      }
      if (url === '/api/stock/locations/2' && init?.method === 'PATCH') {
        locations = locations.map((row) => (row.id === 2 ? { ...row, ...body } : row));
        return reply(200, locations[1]);
      }
      return reply(404, { detail: 'Not found' });
    }),
  );
  return calls;
}

test('lists active and inactive locations and adds a new one', async () => {
  mockApi();
  const user = userEvent.setup();
  render(<LocationsPage />);
  const table = await screen.findByRole('table', { name: 'Locations' });
  expect(within(table).getByText('Inactive')).toBeInTheDocument();

  await user.type(screen.getByLabelText('Name'), 'Store-Chennai-01');
  await user.click(screen.getByRole('button', { name: 'Add location' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('already exists');

  await user.clear(screen.getByLabelText('Name'));
  await user.type(screen.getByLabelText('Name'), 'Warehouse-Bengaluru');
  await user.selectOptions(screen.getByLabelText('Type'), 'warehouse');
  await user.click(screen.getByRole('button', { name: 'Add location' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Warehouse-Bengaluru added.');
  expect(await within(table).findByText('Warehouse-Bengaluru')).toBeInTheDocument();
});

test('reactivates a location', async () => {
  const calls = mockApi();
  const user = userEvent.setup();
  render(<LocationsPage />);
  await user.click(await screen.findByRole('button', { name: 'Edit Old Depot' }));
  await user.click(screen.getByLabelText('Active'));
  await user.click(screen.getByRole('button', { name: 'Save changes' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Old Depot updated.');
  const patch = calls.find((call) => call.init?.method === 'PATCH');
  expect(JSON.parse(String(patch?.init?.body))).toEqual({
    name: 'Old Depot',
    type: 'warehouse',
    address: 'Hosur',
    is_active: true,
  });
});
