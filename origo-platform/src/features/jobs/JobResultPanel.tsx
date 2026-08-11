/**
 * Shows the decrypted-payload preview for a DATA_DELIVERY job, and lets the
 * operator download the actual bytes.
 *
 * Confirmed against the real jobs.py this time, not guessed:
 * - `result_preview` ({frame_count, size_bytes}) is already attached to the job
 *   object by GET /jobs — no extra request needed for the summary shown here.
 * - GET /jobs/{id}/result returns the raw decrypted bytes directly
 *   (media_type="application/octet-stream", Content-Disposition: attachment) —
 *   NOT JSON. The shared `request()` client helper always calls response.json(),
 *   so it can't be used for this endpoint; this component does its own fetch.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/v1';

interface ResultPreview {
  frame_count: number | null;
  size_bytes: number;
}

export function JobResultPanel({
  jobId,
  jobState,
  preview,
}: {
  jobId: string;
  jobState: string;
  preview?: ResultPreview;
}) {
  if (jobState !== 'active') {
    return (
      <>
        <label className="field">Decrypted payload</label>
        <p className="kv-val" style={{ color: 'var(--text-muted)' }}>
          {jobState === 'failed' || jobState === 'timed_out'
            ? 'This delivery did not complete — no payload was decrypted.'
            : 'Waiting for this job to complete.'}
        </p>
      </>
    );
  }

  if (!preview) {
    return (
      <>
        <label className="field">Decrypted payload</label>
        <div className="result-box">No result was recorded for this job.</div>
      </>
    );
  }

  const download = async () => {
    const response = await fetch(`${BASE}/jobs/${jobId}/result`, { credentials: 'include' });
    if (!response.ok) return;
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${jobId}.bin`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      <label className="field">Decrypted payload</label>
      <p className="kv-val" style={{ color: 'var(--text-muted)' }}>
        {preview.size_bytes} bytes
        {preview.frame_count != null ? ` across ${preview.frame_count} frame${preview.frame_count === 1 ? '' : 's'}` : ''}{' '}
        — decrypted on the ground side. This is the payload Origo Terrestrial decrypted, never the
        key it used to do it.
      </p>
      <button className="btn-secondary" onClick={download}>Download</button>
    </>
  );
}
