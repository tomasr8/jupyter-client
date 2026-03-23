import { ServerConnection } from '@jupyterlab/services';

/**
 * A CERNBox share — either incoming (shared with me) or outgoing (shared by me).
 */
export interface IShare {
  id: string;
  /** Display name of the shared folder */
  name: string;
  /** EOS path to navigate to */
  path: string;
  /** 'incoming' = shared with me, 'outgoing' = shared by me */
  direction: 'incoming' | 'outgoing';
  /** Whether this is a regular user/group share or a public link share */
  shareType: 'regular' | 'public';
  /** Current permission role (VIEWER / EDITOR) */
  role?: string;
  /** The user who shared the folder (incoming) */
  sharedBy?: string;
  /** The user(s) the folder is shared with (outgoing) */
  sharedWith?: string[];
}

interface ResourceInfo {
  path?: string;
  name?: string;
}

// Shape of each entry in public_shares from getSharedByMe
interface RawPublicShareItem {
  public_share?: {
    id?: { opaque_id?: string };
    display_name?: string;
    owner?: { opaque_id?: string };
  };
  resource_info?: ResourceInfo;
}

// Shape of each entry in shares from getSharedByMe (regular shares)
interface RawShareItem {
  share?: {
    id?: { opaque_id?: string };
    owner?: { opaque_id?: string };
    grantee?: { opaque_id?: string };
    permissions?: { permissions?: Record<string, boolean> };
  };
  resource_info?: ResourceInfo;
}

// Shape of each entry in shares from getSharedWithMe
interface RawReceivedShareItem {
  received_share?: {
    share?: {
      id?: { opaque_id?: string };
      owner?: { opaque_id?: string };
      creator?: { opaque_id?: string };
      permissions?: { permissions?: Record<string, boolean> };
    };
  };
  resource_info?: ResourceInfo;
}

function inferRole(permissions?: Record<string, boolean>): string {
  if (!permissions) {
    return 'VIEWER';
  }
  // If any write-like permission is true, it's EDITOR
  if (
    permissions.initiate_file_upload ||
    permissions.create_container ||
    permissions.delete
  ) {
    return 'EDITOR';
  }
  return 'VIEWER';
}

/**
 * Fetch the user's shares from CERNBox (both incoming and outgoing).
 */
export async function fetchShares(): Promise<IShare[]> {
  const settings = ServerConnection.makeSettings();

  const [byMeResp, withMeResp] = await Promise.all([
    ServerConnection.makeRequest(settings.baseUrl + 'share/getSharedByMe', {}, settings),
    ServerConnection.makeRequest(settings.baseUrl + 'share/getSharedWithMe', {}, settings)
  ]);

  if (!byMeResp.ok) {
    const data = await byMeResp.json();
    throw new ServerConnection.ResponseError(byMeResp, data.error ?? byMeResp.statusText);
  }
  if (!withMeResp.ok) {
    const data = await withMeResp.json();
    throw new ServerConnection.ResponseError(withMeResp, data.error ?? withMeResp.statusText);
  }

  const byMeData = await byMeResp.json();
  const withMeData = await withMeResp.json();

  // Regular shares (shared with specific user/group)
  const outgoingRegular: IShare[] = ((byMeData.shares ?? []) as RawShareItem[]).map(item => ({
    id: item.share?.id?.opaque_id ?? '',
    name: item.resource_info?.name ?? '',
    path: (item.resource_info?.path ?? '').replace(/^\/eos/, ''),
    direction: 'outgoing' as const,
    shareType: 'regular' as const,
    role: inferRole(item.share?.permissions?.permissions),
    sharedWith: item.share?.grantee?.opaque_id ? [item.share.grantee.opaque_id] : []
  }));

  // Public shares (link-based, no specific grantee)
  const outgoingPublic: IShare[] = ((byMeData.public_shares ?? []) as RawPublicShareItem[]).map(item => ({
    id: item.public_share?.id?.opaque_id ?? '',
    name: item.resource_info?.name ?? item.public_share?.display_name ?? '',
    path: (item.resource_info?.path ?? '').replace(/^\/eos/, ''),
    direction: 'outgoing' as const,
    shareType: 'public' as const,
    sharedWith: []
  }));

  const incoming: IShare[] = ((withMeData.shares ?? []) as RawReceivedShareItem[]).map(item => ({
    id: item.received_share?.share?.id?.opaque_id ?? '',
    name: item.resource_info?.name ?? '',
    path: (item.resource_info?.path ?? '').replace(/^\/eos/, ''),
    direction: 'incoming' as const,
    shareType: 'regular' as const,
    role: inferRole(item.received_share?.share?.permissions?.permissions),
    sharedBy: item.received_share?.share?.owner?.opaque_id
  }));

  console.log('[cs3org/cs3-jupyter-client] Fetched shares:', { outgoingRegular, outgoingPublic, incoming });

  return [...outgoingRegular, ...outgoingPublic, ...incoming];
}

/**
 * Create a share for a resource via POST /share/share.
 */
export async function createShare(
  path: string,
  body: {
    opaque_id: string;
    idp: string;
    role: string;
    grantee_type: string;
  }
): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const resp = await ServerConnection.makeRequest(
    settings.baseUrl + 'share/share?path=' + encodeURIComponent(path),
    {
      method: 'POST',
      body: JSON.stringify(body)
    },
    settings
  );
  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(
      resp,
      data.error ?? resp.statusText
    );
  }
}

/**
 * Update a share via PUT /share/share.
 */
export async function updateShare(
  shareId: string,
  body: { role?: string; display_name?: string }
): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const resp = await ServerConnection.makeRequest(
    settings.baseUrl + 'share/share?share_id=' + encodeURIComponent(shareId),
    {
      method: 'PUT',
      body: JSON.stringify(body)
    },
    settings
  );
  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(
      resp,
      data.error ?? resp.statusText
    );
  }
}

/**
 * Delete a share via DELETE /share/share or /share/link.
 */
export async function deleteShare(
  shareId: string,
  shareType: 'regular' | 'public'
): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const endpoint = shareType === 'public' ? 'share/link' : 'share/share';
  const resp = await ServerConnection.makeRequest(
    settings.baseUrl + endpoint + '?share_id=' + encodeURIComponent(shareId),
    { method: 'DELETE' },
    settings
  );
  if (!resp.ok && resp.status !== 204) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(
      resp,
      data.error ?? resp.statusText
    );
  }
}
