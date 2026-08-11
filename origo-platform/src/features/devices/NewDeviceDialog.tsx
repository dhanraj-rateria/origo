import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface RegisterResponse {
  id: string;
  name: string;
  type: string;
  provisioning_status: string | null;
}

export function NewDeviceDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState<'ORIGO_SPACE' | 'ORIGO_TERRESTRIAL'>('ORIGO_SPACE');
  const [serial, setSerial] = useState('');
  const [mission, setMission] = useState('');
  const [peerSerial, setPeerSerial] = useState('');
  const [result, setResult] = useState<RegisterResponse | null>(null);
  const queryClient = useQueryClient();

  const register = useMutation({
    mutationFn: () =>
      request<RegisterResponse>('/devices', {
        method: 'POST',
        body: {
          name,
          type,
          serial_number: serial,
          mission: mission || undefined,
          peer_serial_number: type === 'ORIGO_TERRESTRIAL' ? peerSerial || undefined : undefined,
        },
      }),
    onSuccess: async (response) => {
      await queryClient.invalidateQueries({ queryKey: ['devices'] });
      // provisioning_status is only ever non-null when the Docker device loop is
      // enabled — that's worth a beat before closing, since "running" vs
      // "provisioning_failed" is exactly the thing an operator needs to know
      // right after registering. If it's null (provisioning disabled, or this is
      // effectively how a real device would register one day), there's nothing
      // to show — close immediately, same as before.
      if (response.provisioning_status == null) {
        onClose();
      } else {
        setResult(response);
      }
    },
  });

  if (result) {
    const succeeded = result.provisioning_status === 'running';
    return (
      <div className="modal-overlay" onClick={onClose}>
        <div className="modal-card" onClick={(e) => e.stopPropagation()}>
          <div className="modal-head">
            <h2>{succeeded ? 'Device registered' : 'Registered, container did not start'}</h2>
            <button className="modal-close" onClick={onClose}>×</button>
          </div>

          <p className="kv-val">
            <strong>{result.name}</strong> is registered
            {succeeded ? ' and its container is running.' : ', but its container failed to start.'}
          </p>

          {!succeeded && (
            <div className="result-box">
              The device row is the source of truth regardless — this only affects the local
              Docker device-loop container. Check <code className="mono">docker ps -a</code> and{' '}
              <code className="mono">docker logs</code> for the container matching this device's
              serial number, or re-check that its paired device (if this is an Origo Terrestrial
              device) is already registered and running.
            </div>
          )}

          <button onClick={onClose}>Done</button>
        </div>
      </div>
    );
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Register device</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <label className="field">Name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Aster-1" />

        <label className="field">Type</label>
        <div className="type-toggle">
          <button className={type === 'ORIGO_SPACE' ? 'on-key' : ''} onClick={() => setType('ORIGO_SPACE')}>
            Origo Space
          </button>
          <button className={type === 'ORIGO_TERRESTRIAL' ? 'on-data' : ''} onClick={() => setType('ORIGO_TERRESTRIAL')}>
            Origo Terrestrial
          </button>
        </div>

        <label className="field">Serial number</label>
        <input value={serial} onChange={(e) => setSerial(e.target.value)} placeholder="SN-001" />

        <label className="field">Mission (optional)</label>
        <input value={mission} onChange={(e) => setMission(e.target.value)} placeholder="Aster constellation" />

        {type === 'ORIGO_TERRESTRIAL' && (
          <>
            <label className="field">Paired Origo Space serial number</label>
            <input
              value={peerSerial}
              onChange={(e) => setPeerSerial(e.target.value)}
              placeholder="SN-001"
            />
            <p className="field-hint">
              Only used by the local Docker device loop, if enabled — that Origo Space device must
              already be registered (and running) before this one.
            </p>
          </>
        )}

        {register.isError && <p className="error-text">Could not register — check the serial number isn't already in use.</p>}

        <button disabled={!name || !serial || register.isPending} onClick={() => register.mutate()}>
          {register.isPending ? 'Registering…' : 'Register device'}
        </button>
      </div>
    </div>
  );
}
