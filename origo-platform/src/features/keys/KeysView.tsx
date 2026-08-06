import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface KeySummary {
  id: string;
  route: string;
  parameter_set: string;
  state: string;
  created: string;
}

export function KeysView() {
  const { data } = useQuery({
    queryKey: ['keys'],
    queryFn: () => request<KeySummary[]>('/keys'),
  });

  return (
    <table>
      <thead><tr><th>Key ID</th><th>Route</th><th>Parameter set</th><th>State</th><th>Created</th></tr></thead>
      <tbody>{(data ?? []).map((item) => (
        <tr key={item.id}><td className="mono">{item.id}</td><td>{item.route}</td><td className="mono text-muted">{item.parameter_set}</td><td><span className={item.state === 'Active' ? 'badge badge-success' : item.state === 'Superseded' ? 'badge badge-neutral' : 'badge badge-warning'}>{item.state}</span></td><td className="text-muted">{item.created}</td></tr>
      ))}</tbody>
    </table>
  );
}
