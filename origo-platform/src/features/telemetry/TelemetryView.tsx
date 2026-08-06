import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface TelemetryItem {
  name: string;
  temperature: string;
  tamper: string;
  self_test: string;
}

export function TelemetryView() {
  const { data } = useQuery({
    queryKey: ['telemetry'],
    queryFn: () => request<TelemetryItem[]>('/telemetry'),
  });

  return (
    <div className="card-grid">
      {(data ?? []).map((item) => (
        <div key={item.name} className="health-card"><p className="name">{item.name}</p><div className="health-row"><span>Temperature</span><span>{item.temperature}</span></div><div className="health-row"><span>Tamper</span><span className="badge badge-success">{item.tamper}</span></div><div className="health-row"><span>Self-test</span><span className={item.self_test === 'Pass' ? 'badge badge-success' : 'badge badge-warning'}>{item.self_test}</span></div></div>
      ))}
    </div>
  );
}
