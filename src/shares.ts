import { ServerConnection } from '@jupyterlab/services';

type GranteeType = 'GRANTEE_TYPE_USER' | 'GRANTEE_TYPE_GROUP' | 'GRANTEE_TYPE_INVALID';
type ShareDirection = 'BY_ME' | 'WITH_ME';
type ShareType = 'REGULAR' | 'PUBLIC';
type ShareState = 'SHARE_STATE_ACCEPTED' | 'SHARE_STATE_PENDING' | 'SHARE_STATE_REJECTED';
export type ShareRole = 'VIEWER' | 'EDITOR';

interface RawUserGrantee {
  type: 'GRANTEE_TYPE_USER';
  user_id: { opaque_id: string };
}

interface RawGroupGrantee {
  type: 'GRANTEE_TYPE_GROUP';
  group_id: { opaque_id: string };
}

export type ResourceType = 'RESOURCE_TYPE_CONTAINER' | 'RESOURCE_TYPE_FILE';

interface RawResourceInfo {
  name: string;
  path: string;
  type?: ResourceType;
}

interface RawUserInfo {
  id: { opaque_id: string };
  mail: string;
  display_name: string;
}

interface RawSharedByMeRegularUser {
  share: {
    id: { opaque_id: string };
    resource_id: { opaque_id: string };
    grantee: RawUserGrantee;
  };
  resource_info: RawResourceInfo;
  grantee_user_info: RawUserInfo;
}

interface RawSharedByMeRegularGroup {
  share: {
    id: { opaque_id: string };
    resource_id: { opaque_id: string };
    grantee: RawGroupGrantee;
  };
  resource_info: RawResourceInfo;
}

type RawSharedByMeRegular = RawSharedByMeRegularUser | RawSharedByMeRegularGroup;

interface RawSharedByMePublic {
  public_share: {
    id: { opaque_id: string };
    resource_id: { opaque_id: string };
  };
  resource_info: RawResourceInfo;
}

interface RawSharedWithMe {
  received_share: {
    state: ShareState | string;
    share: {
      id: { opaque_id: string };
      resource_id: { opaque_id: string };
      grantee: RawUserGrantee | RawGroupGrantee;
      creator: { opaque_id: string };
    };
  };
  resource_info: RawResourceInfo;
}

interface InvalidGrantee {
  type: 'GRANTEE_TYPE_INVALID';
  opaqueId: string;
}
interface GroupGrantee {
  type: 'GRANTEE_TYPE_GROUP';
  opaqueId: string;
}
interface UserGrantee {
  type: 'GRANTEE_TYPE_USER';
  opaqueId: string;
  mail: string;
  displayName: string;
}

type Grantee = InvalidGrantee | GroupGrantee | UserGrantee;

interface _Share {
  shareDirection: ShareDirection;
  shareType: ShareType;
  resourceOpaueId: string;
  resourceType: ResourceType;
  name: string;
  path: string;
  rawPath: string;
}

export interface ByMeRegularShare extends _Share {
  shareDirection: 'BY_ME';
  shareType: 'REGULAR';
  sharedWith: Grantee[];
}

interface ByMePublicShare extends _Share {
  shareDirection: 'BY_ME';
  shareType: 'PUBLIC';
}

interface WithMeRegularShare extends _Share {
  shareDirection: 'WITH_ME';
  shareType: 'REGULAR';
  sharedBy: string;
}

export type Share = ByMeRegularShare | ByMePublicShare | WithMeRegularShare;

export async function fetchShares(): Promise<Share[]> {
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

  const byMeMerged = new Map<string, ByMeRegularShare>();
  for (const share of byMeData.shares as RawSharedByMeRegular[]) {
    const resourceId = share.share.resource_id.opaque_id;
    const sharedWithOpaqueId =
      share.share.grantee.type === 'GRANTEE_TYPE_USER'
        ? share.share.grantee.user_id.opaque_id
        : share.share.grantee.group_id.opaque_id;

    const grantee: Grantee =
      'grantee_user_info' in share
        ? {
            type: 'GRANTEE_TYPE_USER',
            opaqueId: sharedWithOpaqueId,
            mail: share.grantee_user_info.mail,
            displayName: share.grantee_user_info.display_name
          }
        : {
            type: share.share.grantee.type,
            opaqueId: sharedWithOpaqueId
          };

    if (!byMeMerged.has(resourceId)) {
      byMeMerged.set(resourceId, {
        shareDirection: 'BY_ME',
        shareType: 'REGULAR',
        resourceOpaueId: share.share.resource_id.opaque_id,
        resourceType: share.resource_info.type ?? 'RESOURCE_TYPE_CONTAINER',
        name: share.resource_info.name,
        path: share.resource_info.path.slice('/eos'.length), // TODO: Don't hardcode this prefix
        rawPath: share.resource_info.path,
        sharedWith: [grantee]
      });
    } else {
      byMeMerged.get(resourceId)?.sharedWith.push(grantee);
    }
  }

  const byMePublicMerged = new Map<string, ByMePublicShare>();
  for (const share of byMeData.public_shares as RawSharedByMePublic[]) {
    const resourceId = share.public_share.resource_id.opaque_id;
    byMePublicMerged.set(resourceId, {
      shareDirection: 'BY_ME',
      shareType: 'PUBLIC',
      resourceOpaueId: share.public_share.resource_id.opaque_id,
      resourceType: share.resource_info.type ?? 'RESOURCE_TYPE_CONTAINER',
      name: share.resource_info.name,
      path: share.resource_info.path.slice('/eos'.length), // TODO: Don't hardcode this prefix
      rawPath: share.resource_info.path
    });
  }

  const withMeMerged = new Map<string, WithMeRegularShare>();
  for (const share of withMeData.shares as RawSharedWithMe[]) {
    if (share.received_share.state !== 'SHARE_STATE_ACCEPTED') {
      continue; // Skip non-accepted shares
    }
    const resourceId = share.received_share.share.resource_id.opaque_id;
    withMeMerged.set(resourceId, {
      shareDirection: 'WITH_ME',
      shareType: 'REGULAR',
      resourceOpaueId: share.received_share.share.resource_id.opaque_id,
      resourceType: share.resource_info.type ?? 'RESOURCE_TYPE_CONTAINER',
      name: share.resource_info.name,
      path: share.resource_info.path.slice('/eos'.length), // TODO: Don't hardcode this prefix
      rawPath: share.resource_info.path,
      sharedBy: share.received_share.share.creator.opaque_id
    });
  }

  return [...byMeMerged.values(), ...byMePublicMerged.values(), ...withMeMerged.values()];
}

export interface ShareGranteeDetail {
  shareId: string;
  type: GranteeType;
  opaqueId: string;
  role: ShareRole;
  displayName?: string;
}

export interface UserSearchResult {
  opaqueId: string;
  idp: string;
  displayName: string;
  mail: string;
}

export interface GroupSearchResult {
  opaqueId: string;
  displayName: string;
}

function roleFromRawPermissions(permissions: Record<string, unknown> | undefined): ShareRole {
  const perms = (permissions as Record<string, Record<string, unknown>> | undefined)?.permissions;
  return perms?.initiate_file_upload ? 'EDITOR' : 'VIEWER';
}

export async function fetchSharesForResource(rawPath: string): Promise<ShareGranteeDetail[]> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'share/getSharedByResource?' + new URLSearchParams({ path: rawPath });
  const resp = await ServerConnection.makeRequest(url, {}, settings);

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }

  const data = await resp.json();
  const results: ShareGranteeDetail[] = [];

  for (const item of data.shares as RawSharedByMeRegular[]) {
    const grantee = item.share.grantee;
    const opaqueId = grantee.type === 'GRANTEE_TYPE_USER' ? grantee.user_id.opaque_id : grantee.group_id.opaque_id;

    const detail: ShareGranteeDetail = {
      shareId: item.share.id.opaque_id,
      type: grantee.type,
      opaqueId,
      role: roleFromRawPermissions(
        (item.share as Record<string, unknown>).permissions as Record<string, unknown> | undefined
      )
    };

    if ('grantee_user_info' in item) {
      detail.displayName = item.grantee_user_info.display_name;
    }

    results.push(detail);
  }

  return results;
}

export async function removeShare(shareId: string): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'share/share?' + new URLSearchParams({ share_id: shareId });
  const resp = await ServerConnection.makeRequest(url, { method: 'DELETE' }, settings);

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }
}

export async function updateShareRole(shareId: string, role: ShareRole): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'share/share?' + new URLSearchParams({ share_id: shareId });
  const resp = await ServerConnection.makeRequest(
    url,
    {
      method: 'PUT',
      body: JSON.stringify({ role })
    },
    settings
  );

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }
}

export async function createShare(
  rawPath: string,
  opaqueId: string,
  idp: string,
  role: ShareRole,
  granteeType: GranteeType
): Promise<void> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'share/share?' + new URLSearchParams({ path: rawPath });
  const resp = await ServerConnection.makeRequest(
    url,
    {
      method: 'POST',
      body: JSON.stringify({
        opaque_id: opaqueId,
        idp,
        role,
        grantee_type: granteeType === 'GRANTEE_TYPE_USER' ? 'USER' : 'GROUP'
      })
    },
    settings
  );

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }
}

export async function findUsers(query: string, signal?: AbortSignal): Promise<UserSearchResult[]> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'find/users?' + new URLSearchParams({ search: query });
  const resp = await ServerConnection.makeRequest(url, { signal }, settings);

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }

  const data = await resp.json();
  return (data.items as Array<Record<string, unknown>>).map(u => ({
    opaqueId: (u.id as Record<string, string>).opaque_id,
    idp: (u.id as Record<string, string>).idp,
    displayName: (u.display_name as string) || (u.username as string) || '',
    mail: (u.mail as string) || ''
  }));
}

export async function findGroups(query: string, signal?: AbortSignal): Promise<GroupSearchResult[]> {
  const settings = ServerConnection.makeSettings();
  const url = settings.baseUrl + 'find/groups?' + new URLSearchParams({ search: query });
  const resp = await ServerConnection.makeRequest(url, { signal }, settings);

  if (!resp.ok) {
    const data = await resp.json();
    throw new ServerConnection.ResponseError(resp, data.error ?? resp.statusText);
  }

  const data = await resp.json();
  return (data.items as Array<Record<string, unknown>>).map(g => ({
    opaqueId: (g.id as Record<string, string>).opaque_id,
    displayName: (g.group_name as string) || (g.id as Record<string, string>).opaque_id
  }));
}
