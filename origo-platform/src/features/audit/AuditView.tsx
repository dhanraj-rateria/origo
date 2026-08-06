import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface AuditEntry {
  event: string;
  device: string;
  actor: string;
  time: string;
}

export function AuditView() {
  const { data } = useQuery({
    queryKey: ['audit'],
    queryFn: () => request<AuditEntry[]>('/audit'),
  });

  return (
    <>
      <div className="panel" style={{ marginBottom: '20px' }}>
        <h3>Pending approvals</h3>
        <div className="plain-list"><div className="item"><span className="grow">Revoke KEY-8830</span><span className="time">1 of 2 approvals</span></div></div>
      </div>
      <table>
        <thead><tr><th>Event</th><th>Device</th><th>Actor</th><th>Time</th></tr></thead>
        <tbody>{(data ?? []).map((item, index) => (
          <tr key={`${item.event}-${index}`}><td className="mono">{item.event}</td><td>{item.device}</td><td className="text-muted">{item.actor}</td><td className="text-muted">{item.time}</td></tr>
        ))}</tbody>
      </table>
    </>
  );
}
