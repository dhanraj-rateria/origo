import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface DeviceSummary {
  id: string;
  name: string;
  type: string;
  mission: string;
  status: string;
  last_contact: string;
}

export function DevicesView() {
  const { data } = useQuery({
    queryKey: ['devices'],
    queryFn: () => request<DeviceSummary[]>('/devices'),
  });

  return (
    <table>
      <thead><tr><th>Name</th><th>ID</th><th>Type</th><th>Mission</th><th>Status</th><th>Last contact</th></tr></thead>
      <tbody>{(data ?? []).map((device) => (
        <tr key={device.id}><td>{device.name}</td><td className="mono text-muted">{device.id}</td><td>{device.type}</td><td>{device.mission}</td><td><span className="badge badge-success">{device.status}</span></td><td className="text-muted">{device.last_contact}</td></tr>
      ))}</tbody>
    </table>
  );
}
