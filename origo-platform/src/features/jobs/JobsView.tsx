import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';
import { NewJobDialog, type DeviceOption } from './NewJobDialog';
import { JobResultPanel } from './JobResultPanel';

interface ResultPreview {
  frame_count: number | null;
  size_bytes: number;
}

interface JobSummary {
  // Confirmed via a real GET /jobs response: lowercase ("key_exchange",
  // "data_delivery", presumably "config_push"), the opposite casing from what
  // NewJobDialog.tsx POSTs to create one ("KEY_EXCHANGE") — jobs.py's _job_out
  // explicitly lowercases on the way out. Different casing per direction, not a
  // typo — check both directions independently, this is the second time this bit
  // this file.
  type: string;
  state: string;
  satellite_device_id: string;
  ground_device_id: string;
  key_id: string | null;
  created: string;
  failure_reason: string | null;
  // Present only when a DATA_DELIVERY job actually has a decrypted result —
  // confirmed directly from jobs.py's _job_out.
  result_preview?: ResultPreview;
}

const stateLabels: Record<string, string> = {
  scheduled: 'Scheduled',
  active: 'Active',
  failed: 'Failed',
  timed_out: 'Timed out',
};

const stateClass: Record<string, string> = {
  scheduled: 'warning',
  active: 'success',
  failed: 'danger',
  timed_out: 'danger',
};

function renderStateBadge(state: string) {
  return <span className={`badge badge-${stateClass[state] ?? 'neutral'}`}>{stateLabels[state] ?? state}</span>;
}

function renderJobTypeBadge(type: string) {
  if (type === 'key_exchange') return <span className="badge badge-key">Key exchange</span>;
  if (type === 'data_delivery') return <span className="badge badge-data">Data delivery</span>;
  // Not guessing "config_push" is the exact string — show the raw value rather
  // than a label that might not match.
  return <span className="badge badge-neutral">{type}</span>;
}

export function JobsView() {
  const { data } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => request<JobSummary[]>('/jobs'),
  });
  const [selectedJob, setSelectedJob] = useState<JobSummary | null>(null);

  const { data: devices } = useQuery({
    queryKey: ['devices'],
    queryFn: () => request<(DeviceOption & { name: string })[]>('/devices'),
  });

  const [showNewJob, setShowNewJob] = useState(false);

  // There's no `route` field on the real job object — built here from the device
  // list this component already fetches for NewJobDialog.
  const deviceName = (id: string) => devices?.find((d) => d.id === id)?.name ?? id;
  const routeFor = (job: JobSummary) => `${deviceName(job.satellite_device_id)} \u2192 ${deviceName(job.ground_device_id)}`;

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 14 }}>
        <button className="btn-primary" onClick={() => setShowNewJob(true)}>
          + New request
        </button>
      </div>

      {showNewJob && <NewJobDialog devices={devices ?? []} onClose={() => setShowNewJob(false)} />}

      <table>
        <thead>
          <tr>
            <th>Job ID</th>
            <th>Type</th>
            <th>Route</th>
            <th>State</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {(data ?? []).map((job) => (
            <tr key={job.id} className="clickable" onClick={() => setSelectedJob(job)}>
              <td className="mono">{job.id}</td>
              <td>{renderJobTypeBadge(job.type)}</td>
              <td>{routeFor(job)}</td>
              <td>{renderStateBadge(job.state)}</td>
              <td className="text-muted">{job.created}</td>
            </tr>
          ))}
          {data?.length === 0 && (
            <tr>
              <td colSpan={5} className="text-muted">
                No jobs yet — create a key exchange once both devices are registered and active.
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {selectedJob && (
        <div className="modal-overlay" onClick={() => setSelectedJob(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <h2>{selectedJob.id}</h2>
              <button className="modal-close" onClick={() => setSelectedJob(null)}>×</button>
            </div>

            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              {renderJobTypeBadge(selectedJob.type)}
              {renderStateBadge(selectedJob.state)}
            </div>

            <label className="field">Route</label>
            <p className="kv-val">{routeFor(selectedJob)}</p>

            {selectedJob.failure_reason && (
              <>
                <label className="field">Failure reason</label>
                <p className="kv-val" style={{ color: 'var(--danger)' }}>{selectedJob.failure_reason}</p>
              </>
            )}

            {selectedJob.type === 'key_exchange' && (
              <>
                <label className="field">Key material</label>
                <p className="kv-val" style={{ color: 'var(--text-muted)' }}>
                  Not exposed via platform — the derived traffic key lives only in Origo
                  Terrestrial's memory for the lifetime of that process. This page shows job
                  and key *state*, never key material.
                </p>
              </>
            )}

            {selectedJob.type === 'data_delivery' && (
              <JobResultPanel jobId={selectedJob.id} jobState={selectedJob.state} preview={selectedJob.result_preview} />
            )}
          </div>
        </div>
      )}
    </>
  );
}
