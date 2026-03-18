// import { ServerConnection } from '@jupyterlab/services';

/**
 * Storage quota information for the user's CERNBox home.
 */
export interface IQuota {
  /** Bytes used */
  used: number;
  /** Total bytes available */
  total: number;
}

/**
 * Fetch the user's storage quota from the CS3/CERNBox backend.
 */
export async function fetchQuota(): Promise<IQuota> {
  // const settings = ServerConnection.makeSettings();
  // const url = settings.baseUrl + 'quota';
  // const response = await ServerConnection.makeRequest(url, {}, settings);
  // if (!response.ok) {
  //   const data = await response.json();
  //   throw new ServerConnection.ResponseError(response, data.error ?? response.statusText);
  // }
  // const data = await response.json();
  // console.log('[cs3org/cs3-jupyter-client] Fetched quota data:', data);
  // const q = data.quota;
  // return {
  //   used: q.used_bytes ?? 0,
  //   total: q.total_bytes ?? 0
  // };
  return {
    used: 0,
    total: 1
  }
}

/**
 * Format bytes into a human-readable string.
 */
export function formatBytes(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  const units = ['KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = -1;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex++;
  }
  return `${value.toFixed(value >= 100 ? 0 : 1)} ${units[unitIndex]}`;
}
