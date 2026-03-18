import { ServerConnection } from '@jupyterlab/services';

/**
 * A CERNBox Space (project) that the user has access to.
 */
export interface ISpace {
  /** Unique identifier */
  id: string;
  /** Display name */
  name: string;
  /** Optional description */
  description?: string;
  /**
   * Path relative to the ContentsManager root_dir (i.e. /eos).
   * Example: "/project/a/atlas-analysis"
   */
  path: string;
}

/**
 * Fetch the list of spaces the current user has access to.
 */
export async function fetchSpaces(): Promise<ISpace[]> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'space/list';
  const response = await ServerConnection.makeRequest(url, {}, settings);
  if (!response.ok) {
    const data = await response.json();
    throw new ServerConnection.ResponseError(response, data.error ?? response.statusText);
  }
  const data = await response.json();
  interface RawSpace {
    id?: { opaque_id?: string };
    name?: string;
    description?: string;
    root_info?: { path?: string };
  }
  return (data.spaces as RawSpace[]).map(s => ({
    id: s.id?.opaque_id ?? '',
    name: s.name ?? '',
    description: s.description,
    path: s.root_info?.path ?? ''
  }));
}
