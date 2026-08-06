import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface PassSummary {
  reservation_token: string;
  satellite: string;
  ground_station: string;
  band: string;
  aos: string;
  los: string;
  elevation: string;
}

export function PassesView() {
  const { data } = useQuery({
    queryKey: ['passes'],
    queryFn: () => request<PassSummary[]>('/passes'),
  });

  return (
    <table>
      <thead><tr><th>Satellite</th><th>Ground station</th><th>Band</th><th>AOS</th><th>LOS</th><th>Max elevation</th></tr></thead>
      <tbody>{(data ?? []).map((pass, index) => (
        <tr key={pass.reservation_token || index}><td>{pass.satellite}</td><td>{pass.ground_station}</td><td><span className={pass.band === 'Passed' ? 'badge badge-neutral' : 'badge badge-key'}>{pass.band}</span></td><td>{pass.aos}</td><td>{pass.los}</td><td className="text-muted">{pass.elevation}</td></tr>
      ))}</tbody>
    </table>
  );
}
