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

/** Value of the CSRF cookie set at login, echoed in a header on state-changing requests. */
function csrfToken(): string {
  const match = document.cookie.match(/(?:^|; )esims_csrf=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : '';
}

export async function api<T = void>(
  path: string,
  options: { method?: string; body?: unknown } = {},
): Promise<T> {
  const body = options.body;
  const isFormData = body instanceof FormData;
  const method = options.method ?? (body === undefined ? 'GET' : 'POST');
  const headers: Record<string, string> = {};
  if (body !== undefined && !isFormData) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase())) {
    headers['X-CSRF-Token'] = csrfToken();
  }
  const response = await fetch(`/api${path}`, {
    method,
    credentials: 'same-origin',
    headers,
    body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    const fields = Array.isArray(data.detail)
      ? Object.fromEntries(
          data.detail
            .filter((item: unknown) => typeof item === 'object' && item !== null)
            .map(
              (item: {
                loc?: unknown[];
                msg?: unknown;
                line?: unknown;
                field?: unknown;
                message?: unknown;
              }) => [
                String(item.line ?? item.field ?? item.loc?.at(-1) ?? ''),
                String(item.message ?? item.msg ?? ''),
              ],
            ),
        )
      : typeof data.detail === 'object' && data.detail !== null
        ? data.detail
        : {};
    const detail =
      typeof data.detail === 'string'
        ? data.detail
        : Array.isArray(data.detail) || (typeof data.detail === 'object' && data.detail !== null)
          ? 'Please correct the highlighted fields.'
          : 'Something went wrong';
    if (response.status === 401 && !path.startsWith('/auth/login')) {
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw new ApiError(response.status, detail, fields);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** Download a file from the backend, e.g. a report export, and hand it to the browser. */
export async function downloadFile(path: string): Promise<void> {
  const response = await fetch(`/api${path}`, { credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    throw new ApiError(
      response.status,
      typeof data.detail === 'string' ? data.detail : 'Something went wrong',
    );
  }
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const filename = /filename="([^"]+)"/.exec(disposition)?.[1] ?? 'export';
  const url = URL.createObjectURL(await response.blob());
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}
