import { afterEach, describe, expect, it, vi } from 'vitest';

import { api } from './api';

function mockFetch() {
  const fetchMock = vi.fn(async () => new Response('{}', { status: 200 }));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

function sentHeaders(fetchMock: ReturnType<typeof mockFetch>): Record<string, string> {
  const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
  return init.headers as Record<string, string>;
}

describe('api CSRF header', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = 'esims_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/';
  });

  it('sends the CSRF cookie value on state-changing requests', async () => {
    document.cookie = 'esims_csrf=abc123; path=/';
    const fetchMock = mockFetch();
    await api('/sales', { body: { items: [] } });
    expect(sentHeaders(fetchMock)['X-CSRF-Token']).toBe('abc123');
  });

  it('does not send it on reads', async () => {
    document.cookie = 'esims_csrf=abc123; path=/';
    const fetchMock = mockFetch();
    await api('/product');
    expect(sentHeaders(fetchMock)['X-CSRF-Token']).toBeUndefined();
  });
});
