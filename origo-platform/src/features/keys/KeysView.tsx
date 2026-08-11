import { useQuery } from '@tanstack/react-query';
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

// Uppercase — confirmed directly this time (keys.py: state: k.state.value, no
// .lower()), not inferred. jobs.py lowercases; keys.py doesn't. Two sibling
// endpoints, two different conventions — check each independently.
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
  const { data } = useQuery({
    queryKey: ['keys'],
    queryFn: () => request<KeySummary[]>('/keys'),
  });
  // Same missing-field issue jobs.py had: keys.py returns satellite_device_id /
  // ground_device_id, no precomputed route string — resolved here the same way.
  const { data: devices } = useQuery({
    queryKey: ['devices'],
    queryFn: () => request<DeviceRef[]>('/devices'),
  });
  const deviceName = (id: string) => devices?.find((d) => d.id === id)?.name ?? id;

  return (
    <table>
      <thead><tr><th>Key ID</th><th>Route</th><th>Parameter set</th><th>State</th><th>Created</th></tr></thead>
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
          </tr>
        ))}
        {data?.length === 0 && (
          <tr>
            <td colSpan={5} className="text-muted">No keys yet.</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}
