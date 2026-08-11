import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

export interface DeviceOption {
  id: string;
  name: string;
  type: string;
}

export function NewJobDialog({
  devices,
  onClose,
}: {
  devices: DeviceOption[];
  onClose: () => void;
}) {
  const [type, setType] = useState<'KEY_EXCHANGE' | 'DATA_DELIVERY'>('KEY_EXCHANGE');
  const [satelliteId, setSatelliteId] = useState('');
  const [groundId, setGroundId] = useState('');
  const [paramSet, setParamSet] = useState('ML_KEM_1024');
  const queryClient = useQueryClient();

  const createJob = useMutation({
    mutationFn: () =>
      request('/jobs', {
        method: 'POST',
        body: {
          type,
          satellite_device_id: satelliteId,
          ground_device_id: groundId,
          // Only meaningful for KEY_EXCHANGE. DATA_DELIVERY doesn't take a key_id
          // from here either — that's resolved server-side against the pair's
          // currently-ACTIVE key, since an operator creating a delivery job
          // shouldn't need to know an internal key identifier to do it.
          ...(type === 'KEY_EXCHANGE' ? { kem_param_set: paramSet } : {}),
        },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['jobs'] });
      await queryClient.invalidateQueries({ queryKey: ['keys'] });
      onClose();
    },
  });

  const satellites = devices.filter((d) => d.type === 'ORIGO_SPACE');
  const grounds = devices.filter((d) => d.type === 'ORIGO_TERRESTRIAL');

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>New request</h2>
          <button className="modal-close" onClick={onClose}>×</button>
        </div>

        <div className="type-toggle">
          <button className={type === 'KEY_EXCHANGE' ? 'on-key' : ''} onClick={() => setType('KEY_EXCHANGE')}>
            Key exchange
          </button>
          <button className={type === 'DATA_DELIVERY' ? 'on-data' : ''} onClick={() => setType('DATA_DELIVERY')}>
            Data delivery
          </button>
        </div>

        <label className="field">Origo Space device</label>
        <select value={satelliteId} onChange={(e) => setSatelliteId(e.target.value)}>
          <option value="">Select…</option>
          {satellites.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>

        <label className="field">Origo Terrestrial device</label>
        <select value={groundId} onChange={(e) => setGroundId(e.target.value)}>
          <option value="">Select…</option>
          {grounds.map((d) => (
            <option key={d.id} value={d.id}>{d.name}</option>
          ))}
        </select>

        {type === 'KEY_EXCHANGE' && (
          <>
            <label className="field">KEM parameter set</label>
            <select value={paramSet} onChange={(e) => setParamSet(e.target.value)}>
              <option value="ML_KEM_1024">ML-KEM-1024</option>
              <option value="ML_KEM_768">ML-KEM-768</option>
              <option value="ML_KEM_512">ML-KEM-512</option>
            </select>
          </>
        )}

        {type === 'DATA_DELIVERY' && (
          <p className="field-hint" style={{ marginBottom: 14 }}>
            Uses the currently active key for this device pair — run a key exchange first if one
            hasn't completed yet.
          </p>
        )}

        {createJob.isError && (
          <p className="error-text">
            Could not create the job. Check both devices are ACTIVE — and for a data delivery,
            that a key exchange for this pair has already completed.
          </p>
        )}

        <button
          disabled={!satelliteId || !groundId || createJob.isPending}
          onClick={() => createJob.mutate()}
        >
          {createJob.isPending ? 'Creating…' : 'Create job'}
        </button>
      </div>
    </div>
  );
}
