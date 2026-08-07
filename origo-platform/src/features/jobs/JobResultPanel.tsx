import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface JobDetail {
  id: string;
  type: string;
  state: string;
  failure_reason: string | null;
  result_preview?: { frame_count: number; size_bytes: number };
}

export function JobResultPanel({ jobId }: { jobId: string }) {
  const { data: job } = useQuery({
    queryKey: ['jobs', 'detail', jobId],
    queryFn: () => request<JobDetail>(`/jobs/${jobId}`),
    // Poll while the job hasn't reached a terminal state — stop once it has.
    refetchInterval: (query) =>
      query.state.data && ['active', 'failed', 'timed_out'].includes(query.state.data.state) ? false : 5000,
  });

  if (!job) return null;

  if (job.type === 'key_exchange') {
    return job.state === 'active'
      ? <p className="kv-val">Key established. Material never leaves Origo Terrestrial — nothing more to show here by design.</p>
      : <p className="kv-val">{job.state === 'failed' ? job.failure_reason : 'Waiting for the next pass…'}</p>;
  }

  if (job.type === 'data_delivery') {
    if (!job.result_preview) {
      return <p className="kv-val">{job.state === 'failed' ? job.failure_reason : 'No result yet — waiting for the next pass.'}</p>;
    }
    return (
      <div>
        <p className="kv-val">{job.result_preview.frame_count} frames, {job.result_preview.size_bytes} bytes</p>
        <a href={`/v1/jobs/${jobId}/result`} download>
          <button>Download result</button>
        </a>
      </div>
    );
  }

  return null;
}