import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface AlertSummary {
  id: string;
  severity: string;
  device: string;
  condition: string;
  state: string;
  opened: string;
}

export function AlertsView() {
  const { data } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => request<AlertSummary[]>('/alerts'),
  });

  return (
    <table>
      <thead><tr><th>Severity</th><th>Device</th><th>Condition</th><th>State</th><th>Opened</th><th></th></tr></thead>
      <tbody>{(data ?? []).map((item) => (
        <tr key={item.id} id={`alert-${item.id}`}>
          <td><span className={item.severity === 'Warning' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.severity}</span></td>
          <td>{item.device}</td>
          <td className="text-muted">{item.condition}</td>
          <td><span className={item.state === 'Open' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.state}</span></td>
          <td className="text-muted">{item.opened}</td>
          <td>{item.state === 'Open' ? <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12.5px' }}>Acknowledge</button> : null}</td>
        </tr>
      ))}</tbody>
    </table>
  );
}
