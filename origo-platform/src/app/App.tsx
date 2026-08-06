import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';
import { formatUtc, relativeTime } from '@/shared/lib/time';

const navItems = [
  { id: 'overview', label: 'Overview', path: '/overview' },
  { id: 'devices', label: 'Devices', path: '/devices' },
  { id: 'passes', label: 'Passes', path: '/passes' },
  { id: 'jobs', label: 'Jobs', path: '/jobs' },
  { id: 'keys', label: 'Keys', path: '/keys' },
  { id: 'telemetry', label: 'Telemetry', path: '/telemetry' },
  { id: 'policies', label: 'Config & policy', path: '/policies' },
  { id: 'alerts', label: 'Alerts', path: '/alerts' },
  { id: 'audit', label: 'Audit & access', path: '/audit' },
] as const;

export function AppShell() {
  const location = useLocation();
  const { data: overview } = useQuery({
    queryKey: ['overview'],
    queryFn: () => request<{ satellites: number; ground_stations: number; active_keys: number; open_alerts: number }>('/overview'),
  });

  const currentTitle = navItems.find((item) => location.pathname.startsWith(item.path))?.label ?? 'Overview';

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span>Groundlink</span></div>
        <nav>
          <div className="nav-label">Overview</div>
          {navItems.map((item) => (
            <NavLink key={item.id} to={item.path} className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}>
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <h1>{currentTitle}</h1>
          <div className="topbar-actions">
            <div className="search"><input type="text" placeholder="Search devices, jobs, keys..." /></div>
          </div>
        </header>
        <div className="content">
          <div className="status-strip">
            <span>Connected to edge API</span>
            <span>{overview ? `${overview.satellites} sats · ${overview.open_alerts} alerts` : 'Loading…'}</span>
          </div>
          <Outlet />
        </div>
      </main>
    </div>
  );
}

export default AppShell;
