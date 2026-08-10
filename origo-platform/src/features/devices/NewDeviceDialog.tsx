import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

export function NewDeviceDialog({ onClose }: { onClose: () => void }) {
  const [name, setName] = useState('');
  const [type, setType] = useState<'ORIGO_SPACE' | 'ORIGO_TERRESTRIAL'>('ORIGO_SPACE');
  const [serial, setSerial] = useState('');
  const [mission, setMission] = useState('');
  const [peerSerial, setPeerSerial] = useState('');
  const queryClient = useQueryClient();

  const register = useMutation({
    mutationFn: () =>
      request('/devices', {
        method: 'POST',
        body: {
          name,
          type,
          serial_number: serial,
          mission: mission || undefined,
          peer_serial_number: type === 'ORIGO_TERRESTRIAL' ? peerSerial || undefined : undefined,
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['devices'] });
      onClose();
    },
  });

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
