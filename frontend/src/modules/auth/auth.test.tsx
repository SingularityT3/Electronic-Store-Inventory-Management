import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import App from '../../App';
import { api } from '../../api';
import { AuthProvider, can, type User } from '.';

const RAVI: User = {
  id: 1,
  username: 'cashier_ravi',
  full_name: 'Ravi Kumar',
  role: 'cashier',
  location_id: 1,
  permissions: ['products.view', 'sales.record'],
};

/** A fake backend: one account, a session flag, and the auth routes. */
function fakeBackend() {
  const state = { signedIn: false };
  const reply = (status: number, body?: unknown) =>
    Promise.resolve({ ok: status < 400, status, json: async () => body });
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    const body = init?.body ? JSON.parse(init.body as string) : {};
    switch (url) {
      case '/api/auth/me':
        return state.signedIn ? reply(200, RAVI) : reply(401, { detail: 'Not signed in' });
      case '/api/auth/login':
        if (body.username === 'cashier_ravi' && body.password === 'right') {
          state.signedIn = true;
          return reply(200, RAVI);
        }
        return reply(401, { detail: 'Invalid username or password' });
      case '/api/auth/logout':
        state.signedIn = false;
        return reply(204);
      default:
        return reply(404, { detail: 'Not found' });
    }
  });
  vi.stubGlobal('fetch', fetch);
  return state;
}

function renderAt(path: string) {
  render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

async function signIn(password: string) {
  await userEvent.type(await screen.findByLabelText('Username or email'), 'cashier_ravi');
  await userEvent.type(screen.getByLabelText('Password'), password);
  await userEvent.click(screen.getByRole('button', { name: 'Sign in' }));
}

// FR5.2-UT-3
test('an internal URL without a session shows the login page', async () => {
  fakeBackend();
  renderAt('/stock');
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
});

// FR5.2-UT-1
test('valid credentials open the role dashboard', async () => {
  fakeBackend();
  renderAt('/login');
  await signIn('right');
  expect(await screen.findByRole('heading', { name: 'Cashier dashboard' })).toBeInTheDocument();
});

// FR5.2-UT-2
test('invalid credentials show the generic error', async () => {
  fakeBackend();
  renderAt('/login');
  await signIn('wrong');
  expect(await screen.findByRole('alert')).toHaveTextContent('Invalid username or password');
  expect(screen.getByLabelText('Password')).toHaveValue('');
});

test('a signed-in user is already past the login page', async () => {
  const backend = fakeBackend();
  backend.signedIn = true;
  renderAt('/');
  expect(await screen.findByRole('heading', { name: 'Cashier dashboard' })).toBeInTheDocument();
});

// FR5.2-ST-1
test('sign out returns to the login page', async () => {
  const backend = fakeBackend();
  backend.signedIn = true;
  renderAt('/');
  await userEvent.click(await screen.findByRole('button', { name: 'Sign out' }));
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
  expect(backend.signedIn).toBe(false);
});

// FR5.2-IT-1
test('a request rejected for an expired session sends the user to log in', async () => {
  const backend = fakeBackend();
  backend.signedIn = true;
  renderAt('/');
  await screen.findByRole('heading', { name: 'Cashier dashboard' });
  backend.signedIn = false;
  await act(() => expect(api('/auth/me')).rejects.toThrow());
  expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument();
});

test('can() follows the permissions the server sent', () => {
  expect(can(RAVI, 'sales.record')).toBe(true);
  expect(can(RAVI, 'products.manage')).toBe(false);
  expect(can(null, 'products.view')).toBe(false);
});
