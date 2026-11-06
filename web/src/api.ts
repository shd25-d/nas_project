let csrf = '';
export function setCSRF(value: string) { csrf = value; }
export class APIError extends Error { constructor(message: string, public status: number) { super(message); } }

async function failure(response: Response): Promise<never> {
  let message = '요청을 처리하지 못했습니다. 잠시 후 다시 시도하세요.';
  try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch { /* non-JSON response */ }
  if (response.status === 401) window.dispatchEvent(new Event('nas:unauthorized'));
  throw new APIError(message, response.status);
}

export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body) headers.set('Content-Type', 'application/json');
  if (options.method && options.method !== 'GET') headers.set('X-CSRF-Token', csrf);
  const response = await fetch(`/api${path}`, { ...options, headers, credentials: 'same-origin' });
  if (!response.ok) return failure(response);
  return response.json();
}

export function contentURL(path: string, download = false) {
  return `/api/content?${new URLSearchParams({ path, download: String(download) })}`;
}

export async function downloadFile(path: string) {
  // Check the session through the shared error handler, then let the browser stream bytes.
  await api('/session');
  const anchor = document.createElement('a');
  anchor.href = contentURL(path, true);
  anchor.download = path.split('/').pop() || 'download';
  anchor.hidden = true;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

export function upload(file: File, path: string, onProgress: (progress: number) => void, signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const abort = () => xhr.abort();
    const cleanup = () => signal.removeEventListener('abort', abort);
    xhr.open('POST', `/api/upload?${new URLSearchParams({ path, name: file.name })}`);
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');
    xhr.setRequestHeader('X-CSRF-Token', csrf);
    xhr.upload.onprogress = (event) => { if (event.lengthComputable) onProgress(Math.round(event.loaded / event.total * 100)); };
    xhr.onerror = () => { cleanup(); reject(new Error('연결이 끊겼습니다. 네트워크를 확인하세요.')); };
    xhr.onabort = () => { cleanup(); reject(new Error('업로드를 취소했습니다.')); };
    xhr.onload = () => {
      cleanup();
      if (xhr.status >= 200 && xhr.status < 300) { resolve(); return; }
      if (xhr.status === 401) window.dispatchEvent(new Event('nas:unauthorized'));
      let message = '업로드에 실패했습니다.';
      try { message = JSON.parse(xhr.responseText).detail || message; } catch { /* non-JSON response */ }
      reject(new Error(message));
    };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) { cleanup(); reject(new Error('업로드를 취소했습니다.')); return; }
    xhr.send(file);
  });
}

export function bytes(value: number | null) {
  if (value === null) return '—';
  if (value < 1024) return `${value} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let n = value / 1024, i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 ? 1 : 0)} ${units[i]}`;
}
