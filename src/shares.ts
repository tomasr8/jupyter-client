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

// Shape of each entry in shares from getSharedWithMe
interface RawReceivedShareItem {
  received_share?: {
    share?: {
      id?: { opaque_id?: string };
      owner?: { opaque_id?: string };
      creator?: { opaque_id?: string };
    };
  };
  resource_info?: ResourceInfo;
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

  // Public shares (link-based, no specific grantee)
  const outgoing: IShare[] = (byMeData.public_shares as RawPublicShareItem[]).map(item => ({
    id: item.public_share?.id?.opaque_id ?? '',
    name: item.resource_info?.name ?? item.public_share?.display_name ?? '',
    path: (item.resource_info?.path ?? '').replace(/^\/eos/, ''), // Remove leading /eos to get path relative to ContentsManager root_dir
    direction: 'outgoing',
    sharedWith: []
  }));

  const incoming: IShare[] = (withMeData.shares as RawReceivedShareItem[]).map(item => ({
    id: item.received_share?.share?.id?.opaque_id ?? '',
    name: item.resource_info?.name ?? '',
    path: (item.resource_info?.path ?? '').replace(/^\/eos/, ''), // Remove leading /eos to get path relative to ContentsManager root_dir
    direction: 'incoming',
    sharedBy: item.received_share?.share?.owner?.opaque_id
  }));

  console.log('[cs3org/cs3-jupyter-client] Fetched shares:', { outgoing, incoming });

  return [...outgoing, ...incoming];
}
