import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
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
  provisioning_status: string | null;
  deleted_at: string | null;
  last_contact: string | null;
}

const statusBadge: Record<string, string> = {
  ACTIVE: 'badge-success',
  PROVISIONED: 'badge-neutral',
};

function renderProvisioningBadge(status: string | null) {
  if (status === 'running') return <span className="badge badge-success">Container running</span>;
  if (status === 'provisioning_failed') return <span className="badge badge-danger">Provisioning failed</span>;
  if (status === 'deleted') return <span className="badge badge-neutral">Container removed</span>;
  return <span className="badge badge-neutral">—</span>;
}

export function DevicesView() {
  const [showDeleted, setShowDeleted] = useState(false);
  const { data, refetch } = useQuery({
    queryKey: ['devices', showDeleted],
    queryFn: () => request<DeviceSummary[]>(`/devices?deleted=${showDeleted}`),
  });
  const [showNewDevice, setShowNewDevice] = useState(false);
  const queryClient = useQueryClient();

  const deleteDevice = useMutation({
    mutationFn: (id: string) => request(`/devices/${id}`, { method: 'DELETE' }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['devices', true] });
      queryClient.invalidateQueries({ queryKey: ['devices', false] });
    },
  });

  const handleDelete = (device: DeviceSummary) => {
    const warning =
      device.provisioning_status === 'running'
        ? `Delete "${device.name}"? Its Docker container will be stopped and removed. The device ` +
          'record stays in the fleet (marked deleted) — jobs and keys that reference it aren\u2019t affected.'
        : `Delete "${device.name}"? It'll be marked deleted and hidden from the active fleet view.`;
    if (!window.confirm(warning)) return;
    deleteDevice.mutate(device.id, {
      onError: () => window.alert(`Could not delete "${device.name}".`),
    });
  };

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
        <div className="type-toggle">
          <button className={!showDeleted ? 'on-key' : ''} onClick={() => setShowDeleted(false)}>
            Active
          </button>
          <button className={showDeleted ? 'on-data' : ''} onClick={() => setShowDeleted(true)}>
            Deleted
          </button>
        </div>
        {!showDeleted && (
          <button className="btn-primary" onClick={() => setShowNewDevice(true)}>
            + Register device
          </button>
        )}
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
            <th>{showDeleted ? 'Deleted' : 'Last contact'}</th>
            <th></th>
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
              <td className="text-muted">
                {showDeleted ? relativeTime(device.deleted_at) : relativeTime(device.last_contact)}
              </td>
              <td>
                {!showDeleted && (
                  <button
                    disabled={deleteDevice.isPending}
                    onClick={() => handleDelete(device)}
                    title="Delete device"
                    style={{ color: '#c0392b', borderColor: '#c0392b' }}
                  >
                    Delete
                  </button>
                )}
              </td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={9} className="text-muted">
                {showDeleted ? 'No deleted devices.' : 'No devices registered yet.'}
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