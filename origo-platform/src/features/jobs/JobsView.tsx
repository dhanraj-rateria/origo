import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface JobSummary {
  id: string;
  type: 'key' | 'data';
  route: string;
  state: string;
  created: string;
}

const stateLabels: Record<string, string> = {
  active: 'Active',
  completed: 'Completed',
  scheduled: 'Scheduled',
  dispatched: 'Dispatched',
  failed: 'Failed',
  superseded: 'Superseded',
};

const stateClass: Record<string, string> = {
  active: 'success',
  completed: 'success',
  scheduled: 'warning',
  dispatched: 'warning',
  failed: 'danger',
  superseded: 'neutral',
};

function renderStateBadge(state: string) {
  return <span className={`badge badge-${stateClass[state] ?? 'neutral'}`}>{stateLabels[state] ?? state}</span>;
}

function renderJobTypeBadge(type: JobSummary['type']) {
  return type === 'key' ? <span className="badge badge-key">Key exchange</span> : <span className="badge badge-data">Data delivery</span>;
}

export function JobsView() {
  const { data } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => request<JobSummary[]>('/jobs'),
  });
  const [selectedJob, setSelectedJob] = useState<JobSummary | null>(null);

  return (
    <>
      <table>
        <thead><tr><th>Job ID</th><th>Type</th><th>Route</th><th>State</th><th>Created</th></tr></thead>
        <tbody>
          {(data ?? []).map((job) => (
            <tr key={job.id} className="clickable" onClick={() => setSelectedJob(job)}>
              <td className="mono">{job.id}</td>
              <td>{renderJobTypeBadge(job.type)}</td>
              <td>{job.route}</td>
              <td>{renderStateBadge(job.state)}</td>
              <td className="text-muted">{job.created}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {selectedJob ? (
        <div className="modal-overlay" onClick={() => setSelectedJob(null)}>
          <div className="modal-card" onClick={(event) => event.stopPropagation()}>
            <div className="modal-head"><h2 className="mono">{selectedJob.id}</h2><button className="modal-close" onClick={() => setSelectedJob(null)}>×</button></div>
            <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>{renderJobTypeBadge(selectedJob.type)}{renderStateBadge(selectedJob.state)}</div>
            <p className="kv-val" style={{ marginTop: '-8px' }}>{selectedJob.route}</p>
            <p className="kv">Progress</p><p className="kv-val">Scheduled · Dispatched · EK sent · CT received · Active</p>
            <p className="kv">Key material</p><p className="kv-val" style={{ color: 'var(--text-muted)' }}>Not exposed via platform — resides only in HSM secure storage.</p>
          </div>
        </div>
      ) : null}
    </>
  );
}
