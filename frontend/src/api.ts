/** JSON client for the backend API. Sends the session cookie with every request. */

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public fields: Record<string, string> = {},
  ) {
    super(message);
  }
}

/** Fired when a request is rejected because the session is missing or expired. */
export const SESSION_EXPIRED_EVENT = 'esims:session-expired';

export async function api<T = void>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const body = options.body;
  const isFormData = body instanceof FormData;
  const response = await fetch(`/api${path}`, {
    method: options.method ?? (body === undefined ? 'GET' : 'POST'),
    credentials: 'same-origin',
    headers: body === undefined || isFormData ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : typeof data.detail === 'object' && data.detail !== null
          ? 'Please correct the highlighted fields.'
          : 'Something went wrong';
    if (response.status === 401 && !path.startsWith('/auth/login')) {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(
      response.status,
      detail,
      typeof data.detail === 'object' && data.detail !== null ? data.detail : {},
    );
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
