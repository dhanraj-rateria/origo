import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';
import { NewDeviceDialog } from './NewDeviceDialog';
import { relativeTime } from '@/shared/lib/time';

interface DeviceSummary {
  id: string;
  name: string;
  type: string;
  mission: string | null;
  status: string;
  peer_serial_number: string | null;
  // Docker device-loop only — "running" | "provisioning_failed" | null. Always
  // null for a real device, or when the provisioner is disabled — treat null as
  // "no provisioning info to show," not "device unhealthy." See origo-edge's
  // Device model for the full rationale.
  provisioning_status: string | null;
  last_contact: string | null;
}

const statusBadge: Record<string, string> = {
  ACTIVE: 'badge-success',
  PROVISIONED: 'badge-neutral',
  // Only these two are confirmed (ACTIVE at registration, PROVISIONED as the
  // model's default) — anything else falls back to a plain neutral badge below
  // rather than guessing at values from DeviceStatus that weren't directly seen.
};

function renderProvisioningBadge(status: string | null) {
  if (status === 'running') return <span className="badge badge-success">Container running</span>;
  if (status === 'provisioning_failed') return <span className="badge badge-danger">Provisioning failed</span>;
  // Not "not provisioned" as a warning — most real devices, and any device
  // registered with the Docker device loop disabled, will always show this.
  return <span className="badge badge-neutral">—</span>;
}

export function DevicesView() {
  const { data, refetch } = useQuery({
    queryKey: ['devices'],
    queryFn: () => request<DeviceSummary[]>('/devices'),
  });
  const [showNewDevice, setShowNewDevice] = useState(false);

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button className="btn-primary" onClick={() => setShowNewDevice(true)}>
          + Register device
        </button>
      </div>

      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>ID</th>
            <th>Type</th>
            <th>Mission</th>
            <th>Paired with</th>
            <th>Status</th>
            <th>Container</th>
            <th>Last contact</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((device) => (
            <tr key={device.id}>
              <td>{device.name}</td>
              <td className="mono text-muted">{device.id}</td>
              <td>{device.type === 'ORIGO_SPACE' ? 'Origo Space' : 'Origo Terrestrial'}</td>
              <td className={device.mission ? undefined : 'text-muted'}>{device.mission ?? '—'}</td>
              <td className={device.peer_serial_number ? 'mono' : 'text-muted'}>
                {device.peer_serial_number ?? '—'}
              </td>
              <td>
                <span className={`badge ${statusBadge[device.status] ?? 'badge-neutral'}`}>{device.status}</span>
              </td>
              <td>{renderProvisioningBadge(device.provisioning_status)}</td>
              <td className="text-muted">{relativeTime(device.last_contact)}</td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={8} className="text-muted">
                No devices registered yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {showNewDevice && (
        <NewDeviceDialog
          onClose={() => {
            setShowNewDevice(false);
            void refetch();
          }}
        />
      )}
    </>
  );
}
