import { render, screen } from '@testing-library/react';
import App from './App';

test('shows API status from the health route', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ json: async () => ({ status: 'ok' }) }));
  render(<App />);
  expect(await screen.findByText('API status: ok')).toBeInTheDocument();
});
