import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';
import {NewJobDialog, type DeviceOption} from './NewJobDialog';

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
  return (
    <span className={`badge ${type === 'key' ? 'badge-key' : 'badge-data'}`}>
      {type === 'key' ? 'Key exchange' : 'Data delivery'}
    </span>
  );
}

export function JobsView() {
  const { data } = useQuery({
    queryKey: ['jobs'],
    queryFn: () => request<JobSummary[]>('/jobs'),
  });
  const [selectedJob, setSelectedJob] = useState<JobSummary | null>(null);

  const { data: devices } = useQuery({
    queryKey: ['devices'],
    queryFn: () => request<DeviceOption[]>('/devices'),
  });

  const [showNewJob, setShowNewJob] = useState(false);

  return (
    <>
      <button onClick={() => setShowNewJob(true)}>
        + New request
      </button>
      {showNewJob && (
        <NewJobDialog
          devices={devices ?? []}
          onClose={() => setShowNewJob(false)}
        />
      )}
      <table className="table">
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
          <tr
            key={job.id}
            className="clickable"
            onClick={() => setSelectedJob(job)}
          >
            <td>{job.id}</td>
            <td>{renderJobTypeBadge(job.type)}</td>
            <td>{job.route}</td>
            <td>{renderStateBadge(job.state)}</td>
            <td>{job.created}</td>
          </tr>
        ))}
      </tbody>
    </table>
      {selectedJob && (
    <div
      className="modal-overlay"
      onClick={() => setSelectedJob(null)}
    >
      <div
        className="modal-card"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h2>{selectedJob.id}</h2>

          <button
            className="modal-close"
            onClick={() => setSelectedJob(null)}
          >
            ×
          </button>
        </div>

        <div
          style={{
            display: 'flex',
            gap: 8,
            marginBottom: 16,
          }}
        >
          {renderJobTypeBadge(selectedJob.type)}
          {renderStateBadge(selectedJob.state)}
        </div>

        <label>Route</label>
        <p className="kv-val">{selectedJob.route}</p>

        <label>Progress</label>
        <p className="kv-val">
          Scheduled → Dispatched → EK sent → CT received → Active
        </p>

        <label>Key material</label>
        <p
          className="kv-val"
          style={{ color: 'var(--text-muted)' }}
        >
          Not exposed via platform — resides only in HSM secure storage.
        </p>
      </div>
    </div>
  )}
    </>
  );
}
