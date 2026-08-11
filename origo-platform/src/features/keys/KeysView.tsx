import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface KeySummary {
  id: string;
  satellite_device_id: string;
  ground_device_id: string;
  parameter_set: string;
  state: string;
  created: string;
}

interface DeviceRef {
  id: string;
  name: string;
}

// Uppercase — confirmed directly (keys.py: state: k.state.value, no .lower()).
const stateClass: Record<string, string> = {
  ACTIVE: 'success',
  PENDING_KEYGEN: 'warning',
  EK_SENT: 'warning',
  AWAITING_CT: 'warning',
  DECAPS_COMPLETE: 'warning',
  SUPERSEDED: 'neutral',
  REVOKED: 'danger',
  DESTROYED: 'neutral',
};

const stateLabels: Record<string, string> = {
  ACTIVE: 'Active',
  PENDING_KEYGEN: 'Pending keygen',
  EK_SENT: 'Ek sent',
  AWAITING_CT: 'Awaiting ct',
  DECAPS_COMPLETE: 'Decaps complete',
  SUPERSEDED: 'Superseded',
  REVOKED: 'Revoked',
  DESTROYED: 'Destroyed',
};

export function KeysView() {
  const [showRevoked, setShowRevoked] = useState(false);
  const { data } = useQuery({
    queryKey: ['keys', showRevoked],
    queryFn: () => request<KeySummary[]>(`/keys?revoked=${showRevoked}`),
  });
  const { data: devices } = useQuery({
    queryKey: ['devices', false],
    queryFn: () => request<DeviceRef[]>('/devices?deleted=false'),
  });
  const deviceName = (id: string) => devices?.find((d) => d.id === id)?.name ?? id;

  const queryClient = useQueryClient();
  const revokeKey = useMutation({
    mutationFn: (id: string) => request(`/keys/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['keys', true] });
      queryClient.invalidateQueries({ queryKey: ['keys', false] });
    },
  });

  const handleRevoke = (key: KeySummary) => {
    const warning =
      key.state === 'ACTIVE'
        ? 'This key is ACTIVE. Revoking it stays in the table (state becomes REVOKED) — but ' +
          "won't reach into Origo Terrestrial's memory, where the actual traffic key stays live " +
          'until that container restarts. A future data-delivery job for this pair will find no ' +
          'active key here and trigger a fresh exchange. Revoke anyway?'
        : 'Revoke this key?';
    if (!window.confirm(warning)) return;
    revokeKey.mutate(key.id, {
      onError: () =>
        window.alert(
          'Could not revoke this key \u2014 it may already be SUPERSEDED (only SUPERSEDED \u2192 DESTROYED is a valid next state).',
        ),
    });
  };

  return (
    <>
      <div className="type-toggle" style={{ marginBottom: 14 }}>
        <button className={!showRevoked ? 'on-key' : ''} onClick={() => setShowRevoked(false)}>
          Active
        </button>
        <button className={showRevoked ? 'on-data' : ''} onClick={() => setShowRevoked(true)}>
          Revoked
        </button>
      </div>

      <table>
        <thead><tr><th>Key ID</th><th>Route</th><th>Parameter set</th><th>State</th><th>Created</th><th></th></tr></thead>
        <tbody>
          {(data ?? []).map((item) => (
            <tr key={item.id}>
              <td className="mono">{item.id}</td>
              <td>{deviceName(item.satellite_device_id)} &#8594; {deviceName(item.ground_device_id)}</td>
              <td className="mono text-muted">{item.parameter_set}</td>
              <td>
                <span className={`badge badge-${stateClass[item.state] ?? 'neutral'}`}>
                  {stateLabels[item.state] ?? item.state}
                </span>
              </td>
              <td className="text-muted">{item.created}</td>
              <td>
                {!showRevoked && (
                  <button
                    disabled={revokeKey.isPending}
                    onClick={() => handleRevoke(item)}
                    title="Revoke key"
                    style={{ color: '#c0392b', borderColor: '#c0392b' }}
                  >
                    Revoke
                  </button>
                )}
              </td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={6} className="text-muted">
                {showRevoked ? 'No revoked keys.' : 'No keys yet.'}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </>
  );
}