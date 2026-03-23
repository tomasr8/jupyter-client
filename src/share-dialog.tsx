import React, { useState, useEffect, useRef, useCallback } from 'react';
import { ServerConnection } from '@jupyterlab/services';

interface IUserOrGroup {
  display_name?: string;
  opaque_id: string;
  idp: string;
  type: 'USER' | 'GROUP';
  // user fields
  username?: string;
  mail?: string;
  // group fields
  group_name?: string;
}

export interface IShareFormData {
  opaque_id: string;
  idp: string;
  role: string;
  grantee_type: string;
}

/**
 * Body widget for the Share dialog.
 * Provides a search input to find users/groups and a role selector.
 */
export function ShareDialogBody(props: {
  folderPath: string;
  onChange: (data: IShareFormData | null) => void;
}): React.ReactElement {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<IUserOrGroup[]>([]);
  const [selected, setSelected] = useState<IUserOrGroup | null>(null);
  const [role, setRole] = useState('VIEWER');
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const search = useCallback(async (q: string) => {
    if (q.length < 2) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const settings = ServerConnection.makeSettings();
      const [usersResp, groupsResp] = await Promise.all([
        ServerConnection.makeRequest(
          settings.baseUrl + 'find/users?search=' + encodeURIComponent(q),
          {},
          settings
        ),
        ServerConnection.makeRequest(
          settings.baseUrl + 'find/groups?search=' + encodeURIComponent(q),
          {},
          settings
        )
      ]);
      const usersData = usersResp.ok ? await usersResp.json() : { items: [] };
      const groupsData = groupsResp.ok ? await groupsResp.json() : { items: [] };

      const users: IUserOrGroup[] = (usersData.items ?? []).map(
        (u: Record<string, unknown>) => ({
          display_name:
            (u.display_name as string) || (u.username as string) || '',
          opaque_id: (u.id as Record<string, string>)?.opaque_id ?? '',
          idp: (u.id as Record<string, string>)?.idp ?? '',
          username: u.username as string,
          mail: u.mail as string,
          type: 'USER' as const
        })
      );
      const groups: IUserOrGroup[] = (groupsData.items ?? []).map(
        (g: Record<string, unknown>) => ({
          display_name:
            (g.display_name as string) || (g.group_name as string) || '',
          opaque_id: (g.id as Record<string, string>)?.opaque_id ?? '',
          idp: (g.id as Record<string, string>)?.idp ?? '',
          group_name: g.group_name as string,
          type: 'GROUP' as const
        })
      );
      setResults([...users, ...groups]);
    } catch (err) {
      console.error('[cs3org/cs3-jupyter-client] Search error:', err);
      setResults([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }
    debounceRef.current = setTimeout(() => search(query), 300);
    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
  }, [query, search]);

  useEffect(() => {
    if (selected) {
      props.onChange({
        opaque_id: selected.opaque_id,
        idp: selected.idp,
        role,
        grantee_type: selected.type
      });
    } else {
      props.onChange(null);
    }
  }, [selected, role]);

  const handleSelect = (item: IUserOrGroup) => {
    setSelected(item);
    setQuery(item.display_name ?? item.opaque_id);
    setResults([]);
  };

  const handleClear = () => {
    setSelected(null);
    setQuery('');
    setResults([]);
  };

  return (
    <div className="swan-share-dialog">
      <div className="swan-share-dialog-field">
        <label className="swan-share-dialog-label">Share with</label>
        <div className="swan-share-dialog-search-wrapper">
          <input
            className="swan-share-dialog-input"
            type="text"
            placeholder="Search users or groups..."
            value={query}
            onChange={e => {
              setQuery(e.target.value);
              if (selected) {
                setSelected(null);
              }
            }}
          />
          {selected && (
            <button
              className="swan-share-dialog-clear-btn"
              onClick={handleClear}
              title="Clear selection"
            >
              x
            </button>
          )}
        </div>
        {!selected && results.length > 0 && (
          <ul className="swan-share-dialog-results">
            {results.map((item, i) => (
              <li
                key={`${item.type}-${item.opaque_id}-${i}`}
                className="swan-share-dialog-result-item"
                onClick={() => handleSelect(item)}
              >
                <span className="swan-share-dialog-result-type">
                  {item.type === 'GROUP' ? 'Group' : 'User'}
                </span>
                <span className="swan-share-dialog-result-name">
                  {item.display_name}
                </span>
                {item.mail && (
                  <span className="swan-share-dialog-result-detail">
                    {item.mail}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        {!selected && loading && (
          <div className="swan-share-dialog-loading">Searching...</div>
        )}
      </div>

      <div className="swan-share-dialog-field">
        <label className="swan-share-dialog-label">Permission</label>
        <select
          className="swan-share-dialog-select"
          value={role}
          onChange={e => setRole(e.target.value)}
        >
          <option value="VIEWER">Viewer</option>
          <option value="EDITOR">Editor</option>
        </select>
      </div>

      {selected && (
        <div className="swan-share-dialog-summary">
          Share <strong>{props.folderPath}</strong> with{' '}
          <strong>{selected.display_name}</strong> as{' '}
          <strong>{role.toLowerCase()}</strong>
        </div>
      )}
    </div>
  );
}
