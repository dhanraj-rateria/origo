import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface OverviewData {
  satellites: number;
  ground_stations: number;
  active_keys: number;
  open_alerts: number;
}

interface PassSummary {
  reservation_token: string;
  satellite: string;
  ground_station: string;
  band: string;
  aos: string;
  los: string;
  elevation: string;
}

interface AlertSummary {
  id: string;
  severity: string;
  device: string;
  condition: string;
  state: string;
  opened: string;
}

export function OverviewView() {
  const { data: overview } = useQuery({
    queryKey: ['overview-view'],
    queryFn: () => request<OverviewData>('/overview'),
  });
  const { data: passes } = useQuery({
    queryKey: ['passes-overview'],
    queryFn: () => request<PassSummary[]>('/passes'),
  });
  const { data: alerts } = useQuery({
    queryKey: ['alerts-overview'],
    queryFn: () => request<AlertSummary[]>('/alerts'),
  });

  return (
    <>
      <div className="stat-grid">
        <div className="stat-card"><p className="label">Satellites</p><p className="value">{overview?.satellites ?? 0}</p></div>
        <div className="stat-card"><p className="label">Ground stations</p><p className="value">{overview?.ground_stations ?? 0}</p></div>
        <div className="stat-card"><p className="label">Active keys</p><p className="value">{overview?.active_keys ?? 0}</p></div>
        <div className="stat-card"><p className="label">Open alerts</p><p className="value">{overview?.open_alerts ?? 0}</p></div>
      </div>
      <div className="two-col">
        <div className="panel">
          <h3>Upcoming passes</h3>
          <div className="plain-list">
            {(passes ?? []).slice(0, 3).map((item, index) => (
              <div key={item.reservation_token || index} className="item"><span className="badge badge-key">{item.band}</span><span className="grow">{item.satellite} → {item.ground_station}</span><span className="time">{item.aos}</span></div>
            ))}
          </div>
        </div>
        <div className="panel">
          <h3>Recent alerts</h3>
          <div className="plain-list">
            {(alerts ?? []).slice(0, 2).map((item) => (
              <div key={item.id} className="item"><span className={item.severity === 'Warning' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.severity}</span><span className="grow">{item.device} — {item.condition}</span><span className="time">{item.opened}</span></div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
