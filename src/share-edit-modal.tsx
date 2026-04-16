import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { createPortal } from 'react-dom';
import { ReactWidget } from '@jupyterlab/ui-components';
import { Widget } from '@lumino/widgets';
import {
  ShareGranteeDetail,
  ShareRole,
  UserSearchResult,
  GroupSearchResult,
  fetchSharesForResource,
  removeShare,
  updateShareRole,
  createShare,
  findUsers,
  findGroups
} from './shares';
import { createDebouncedFetcher } from './debounce';

export interface ShareTarget {
  name: string;
  rawPath: string;
}

const VIEW_ICON = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
    <circle cx="12" cy="12" r="3" />
  </svg>
);
const EDIT_ICON = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <path d="M17 3a2.83 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5L17 3z" />
  </svg>
);
const TRASH_ICON = (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    width="14"
    height="14"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
  >
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6" />
    <path d="M10 11v6" />
    <path d="M14 11v6" />
    <path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
  </svg>
);

const ROLE_OPTIONS: { value: ShareRole; label: string; icon: React.ReactElement }[] = [
  { value: 'VIEWER', label: 'Can view', icon: VIEW_ICON },
  { value: 'EDITOR', label: 'Can edit', icon: EDIT_ICON }
];

function RoleDropdown({
  value,
  onChange,
  disabled
}: {
  value: ShareRole;
  onChange: (role: ShareRole) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);
  const ref = useRef<HTMLDivElement>(null);
  const opt = ROLE_OPTIONS.find(o => o.value === value) ?? ROLE_OPTIONS[0];

  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, []);

  const handleToggle = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (disabled) return;
    if (!open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      setMenuPos({ top: rect.bottom + 2, left: rect.left });
    }
    setOpen(!open);
  };

  return (
    <div className="swan-shares-role-dropdown" ref={ref}>
      <button
        type="button"
        className="swan-shares-role-dropdown-selected"
        onClick={handleToggle}
        style={disabled ? { opacity: 0.5, cursor: 'not-allowed' } : undefined}
      >
        {opt.icon}
        <span>{opt.label}</span>
      </button>
      {open &&
        menuPos &&
        createPortal(
          <div
            className="swan-shares-role-dropdown-menu"
            style={{ position: 'fixed', top: menuPos.top, left: menuPos.left }}
          >
            {ROLE_OPTIONS.map(o => (
              <div
                key={o.value}
                className={`swan-shares-role-dropdown-option${o.value === value ? ' swan-shares-role-dropdown-option-active' : ''}`}
                onClick={e => {
                  e.stopPropagation();
                  onChange(o.value);
                  setOpen(false);
                }}
              >
                {o.icon}
                <span>{o.label}</span>
              </div>
            ))}
          </div>,
          document.body
        )}
    </div>
  );
}

function GranteeItem({
  grantee,
  onRoleChange,
  onRemove
}: {
  grantee: ShareGranteeDetail;
  onRoleChange: (shareId: string, role: ShareRole) => Promise<void>;
  onRemove: (shareId: string) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [role, setRole] = useState(grantee.role);

  const handleRole = async (newRole: ShareRole) => {
    setBusy(true);
    try {
      await onRoleChange(grantee.shareId, newRole);
      setRole(newRole);
    } catch {
      setRole(role);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="swan-shares-grantee-item">
      <div className="swan-shares-grantee-info">
        <span className="swan-shares-grantee-icon" title={grantee.type === 'GRANTEE_TYPE_USER' ? 'User' : 'Group'}>
          {grantee.type === 'GRANTEE_TYPE_USER' ? '\ud83d\udc64' : '\ud83d\udc65'}
        </span>
        <span className="swan-shares-grantee-name">
          {'displayName' in grantee ? grantee.displayName : grantee.opaqueId}
        </span>
      </div>
      <RoleDropdown value={role} onChange={handleRole} disabled={busy} />
      <button className="swan-shares-grantee-remove" title="Remove" onClick={() => onRemove(grantee.shareId)}>
        {TRASH_ICON}
      </button>
    </div>
  );
}

function SearchResultItem({
  icon,
  name,
  detail,
  alreadyAdded,
  onAdd
}: {
  icon: string;
  iconTitle: string;
  name: string;
  detail?: string;
  alreadyAdded: boolean;
  onAdd: () => Promise<void>;
}) {
  const [state, setState] = useState<'idle' | 'adding' | 'added'>(alreadyAdded ? 'added' : 'idle');

  useEffect(() => {
    setState(prev => (prev === 'adding' ? prev : alreadyAdded ? 'added' : 'idle'));
  }, [alreadyAdded]);

  const handleAdd = async () => {
    setState('adding');
    try {
      await onAdd();
      setState('added');
    } catch {
      setState('idle');
    }
  };

  return (
    <div className="swan-shares-search-result-item">
      <span className="swan-shares-grantee-icon">{icon}</span>
      <div className="swan-shares-search-result-info">
        <div className="swan-shares-search-result-name">{name}</div>
        {detail && <div className="swan-shares-search-result-detail">{detail}</div>}
      </div>
      <button className="swan-shares-search-result-add" disabled={state !== 'idle'} onClick={handleAdd}>
        {state === 'adding' ? 'Adding...' : state === 'added' ? 'Added' : 'Add'}
      </button>
    </div>
  );
}

function EditShareModalContent({ share, onClose }: { share: ShareTarget; onClose: () => void }) {
  const [grantees, setGrantees] = useState<ShareGranteeDetail[]>([]);
  const [granteesLoading, setGranteesLoading] = useState(true);
  const [granteesError, setGranteesError] = useState<string | null>(null);
  const [addRole, setAddRole] = useState<ShareRole>('VIEWER');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<{ users: UserSearchResult[]; groups: GroupSearchResult[] } | null>(
    null
  );
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [status, setStatus] = useState<{ msg: string; isError: boolean } | null>(null);
  const fetcher = useMemo(() => createDebouncedFetcher(300), []);

  const showStatus = useCallback((msg: string, isError = false) => {
    setStatus({ msg, isError });
    if (!isError) {
      setTimeout(() => setStatus(prev => (prev?.msg === msg ? null : prev)), 3000);
    }
  }, []);

  const loadGrantees = useCallback(
    async (silent = false) => {
      if (!silent) {
        setGranteesLoading(true);
        setGranteesError(null);
      }
      try {
        const data = await fetchSharesForResource(share.rawPath);
        setGrantees(data);
      } catch (err) {
        if (!silent) {
          setGranteesError(err instanceof Error ? err.message : 'Failed to load');
        }
      } finally {
        if (!silent) {
          setGranteesLoading(false);
        }
      }
    },
    [share.rawPath]
  );

  useEffect(() => {
    loadGrantees();
  }, [loadGrantees]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (query.length < 2) {
      setSearchResults(null);
      setSearchLoading(false);
      setSearchError(null);
      return fetcher.cancel;
    }
    fetcher.run(async signal => {
      setSearchLoading(true);
      try {
        const [users, groups] = await Promise.all([findUsers(query, signal), findGroups(query, signal)]);
        setSearchResults({ users, groups });
        setSearchError(null);
      } catch (err) {
        if (signal.aborted) return;
        setSearchError(err instanceof Error ? err.message : 'Search failed');
        setSearchResults(null);
      } finally {
        if (!signal.aborted) setSearchLoading(false);
      }
    });
    return fetcher.cancel;
  }, [searchQuery, fetcher]);

  const handleRoleChange = async (shareId: string, newRole: ShareRole) => {
    try {
      await updateShareRole(shareId, newRole);
      setGrantees(prev => prev.map(g => (g.shareId === shareId ? { ...g, role: newRole } : g)));
    } catch (err) {
      showStatus(`Failed to update role: ${err instanceof Error ? err.message : 'Unknown error'}`, true);
      throw err;
    }
  };

  const handleRemove = async (shareId: string) => {
    try {
      await removeShare(shareId);
      setGrantees(prev => prev.filter(g => g.shareId !== shareId));
    } catch (err) {
      showStatus(`Failed to remove: ${err instanceof Error ? err.message : 'Unknown error'}`, true);
    }
  };

  const handleAddUser = async (user: UserSearchResult) => {
    try {
      await createShare(share.rawPath, user.opaqueId, user.idp, addRole, 'GRANTEE_TYPE_USER');
      setGrantees(prev => [
        ...prev,
        { shareId: `pending-${user.opaqueId}`, type: 'GRANTEE_TYPE_USER', opaqueId: user.opaqueId, role: addRole }
      ]);
      loadGrantees(true);
    } catch (err) {
      showStatus(`Failed to add: ${err instanceof Error ? err.message : 'Unknown error'}`, true);
      throw err;
    }
  };

  const handleAddGroup = async (group: GroupSearchResult) => {
    try {
      await createShare(share.rawPath, group.opaqueId, '', addRole, 'GRANTEE_TYPE_GROUP');
      setGrantees(prev => [
        ...prev,
        { shareId: `pending-${group.opaqueId}`, type: 'GRANTEE_TYPE_GROUP', opaqueId: group.opaqueId, role: addRole }
      ]);
      loadGrantees(true);
    } catch (err) {
      showStatus(`Failed to add: ${err instanceof Error ? err.message : 'Unknown error'}`, true);
      throw err;
    }
  };

  return (
    <div
      className="swan-shares-modal-overlay"
      onMouseDown={e => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="swan-shares-modal">
        <div className="swan-shares-modal-header">
          <h3 className="swan-shares-modal-title">Share: {share.name}</h3>
          <button className="swan-shares-modal-close-btn" onClick={onClose}>
            {'\u00d7'}
          </button>
        </div>

        <div className="swan-shares-modal-body">
          {/* Search section */}
          <div className="swan-shares-modal-section">
            <div className="swan-shares-modal-section-title">Share with people</div>
            <div className="swan-shares-search-container">
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '6px' }}>
                <RoleDropdown value={addRole} onChange={setAddRole} />
              </div>
              <input
                className="swan-shares-search-input"
                type="text"
                placeholder="Search users or groups..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
              />
              <div className="swan-shares-search-results">
                {searchLoading && <div className="swan-shares-modal-empty">Searching...</div>}
                {searchError && (
                  <div className="swan-shares-modal-empty" style={{ color: 'var(--jp-error-color1)' }}>
                    {searchError}
                  </div>
                )}
                {searchResults &&
                  !searchLoading &&
                  searchResults.users.length === 0 &&
                  searchResults.groups.length === 0 && <div className="swan-shares-modal-empty">No results found</div>}
                {searchResults && !searchLoading && (
                  <>
                    {searchResults.users.map(user => (
                      <SearchResultItem
                        key={`user-${user.opaqueId}`}
                        icon={'\ud83d\udc64'}
                        iconTitle="User"
                        name={user.displayName || user.opaqueId}
                        detail={user.mail || undefined}
                        alreadyAdded={grantees.some(
                          g => g.type === 'GRANTEE_TYPE_USER' && g.opaqueId === user.opaqueId
                        )}
                        onAdd={() => handleAddUser(user)}
                      />
                    ))}
                    {searchResults.groups.map(group => (
                      <SearchResultItem
                        key={`group-${group.opaqueId}`}
                        icon={'\ud83d\udc65'}
                        iconTitle="Group"
                        name={group.displayName}
                        alreadyAdded={grantees.some(
                          g => g.type === 'GRANTEE_TYPE_GROUP' && g.opaqueId === group.opaqueId
                        )}
                        onAdd={() => handleAddGroup(group)}
                      />
                    ))}
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Grantees section - hidden when empty */}
          {!granteesLoading && !granteesError && grantees.length > 0 && (
            <div className="swan-shares-modal-section">
              <div className="swan-shares-modal-section-title">Shared with</div>
              <div className="swan-shares-grantee-list">
                {grantees.map(g => (
                  <GranteeItem key={g.shareId} grantee={g} onRoleChange={handleRoleChange} onRemove={handleRemove} />
                ))}
              </div>
            </div>
          )}
          {granteesLoading && <div className="swan-shares-modal-empty">Loading...</div>}
          {granteesError && (
            <div className="swan-shares-modal-empty" style={{ color: 'var(--jp-error-color1)' }}>
              {granteesError}
            </div>
          )}

          {status && (
            <div
              className="swan-shares-modal-status"
              style={{ color: status.isError ? 'var(--jp-error-color1)' : 'var(--jp-ui-font-color2)' }}
            >
              {status.msg}
            </div>
          )}
        </div>

        <div className="swan-shares-modal-footer">
          <button className="swan-shares-modal-footer-btn" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

let activeModal: Widget | null = null;

export function openEditShareModal(share: ShareTarget, onClose: () => void): void {
  if (activeModal) {
    activeModal.dispose();
    activeModal = null;
  }

  const widget = ReactWidget.create(
    <EditShareModalContent
      share={share}
      onClose={() => {
        widget.dispose();
        activeModal = null;
        onClose();
      }}
    />
  );
  activeModal = widget;
  Widget.attach(widget, document.body);
}
