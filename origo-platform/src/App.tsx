import { useEffect, useMemo, useState } from 'react';

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://localhost:8000/api';

const navItems = [
  { id: 'overview', label: 'Overview' },
  { id: 'devices', label: 'Devices' },
  { id: 'passes', label: 'Passes' },
  { id: 'jobs', label: 'Jobs' },
  { id: 'keys', label: 'Keys' },
  { id: 'telemetry', label: 'Telemetry' },
  { id: 'config', label: 'Config & policy' },
  { id: 'alerts', label: 'Alerts' },
  { id: 'audit', label: 'Audit & access' },
] as const;

type ViewId = (typeof navItems)[number]['id'];

const stateLabels = {
  active: 'Active',
  completed: 'Completed',
  scheduled: 'Scheduled',
  dispatched: 'Dispatched',
  failed: 'Failed',
  superseded: 'Superseded',
} as const;

const stateClass = {
  active: 'success',
  completed: 'success',
  scheduled: 'warning',
  dispatched: 'warning',
  failed: 'danger',
  superseded: 'neutral',
} as const;

type JobType = 'key' | 'data';

type Job = {
  id: string;
  type: JobType;
  route: string;
  state: keyof typeof stateLabels;
  created: string;
};

type Policy = {
  name: string;
  mission: string;
  trigger: string;
  parameter_set: string;
  value: string;
};

type Alert = {
  id: string;
  severity: string;
  device: string;
  condition: string;
  state: string;
  opened: string;
};

const fetchJson = async <T,>(path: string): Promise<T> => {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
};

const App = () => {
  const [view, setView] = useState<ViewId>('overview');
  const [overview, setOverview] = useState<Record<string, number>>({});
  const [devices, setDevices] = useState<any[]>([]);
  const [passes, setPasses] = useState<Array<{ reservation_token: string; satellite: string; ground_station: string; band: string; aos: string; los: string; elevation: string;}>>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keys, setKeys] = useState<any[]>([]);
  const [telemetry, setTelemetry] = useState<any[]>([]);
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [audit, setAudit] = useState<any[]>([]);
  const [showModal, setShowModal] = useState(false);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [requestType, setRequestType] = useState<JobType>('key');

  useEffect(() => {
    fetchJson<{ satellites: number; ground_stations: number; active_keys: number; open_alerts: number }>('/overview').then(setOverview).catch(console.error);
    fetchJson('/devices').then(setDevices).catch(console.error);
    fetchJson('/passes').then(setPasses).catch(console.error);
    fetchJson('/jobs').then(setJobs).catch(console.error);
    fetchJson('/keys').then(setKeys).catch(console.error);
    fetchJson('/telemetry').then(setTelemetry).catch(console.error);
    fetchJson('/policies').then(setPolicies).catch(console.error);
    fetchJson('/alerts').then(setAlerts).catch(console.error);
    fetchJson('/audit').then(setAudit).catch(console.error);
  }, []);

  const activeButtonClass = (id: ViewId) => `nav-item${id === view ? ' active' : ''}`;

  const renderJobTypeBadge = (type: JobType) =>
    type === 'key' ? <span className="badge badge-key">Key exchange</span> : <span className="badge badge-data">Data delivery</span>;

  const renderStateBadge = (state: keyof typeof stateLabels) => (
    <span className={`badge badge-${stateClass[state]}`}>{stateLabels[state]}</span>
  );

  const openJobDetail = (job: Job) => {
    setSelectedJob(job);
    setShowModal(true);
  };

  const closeModal = () => {
    setShowModal(false);
    setSelectedJob(null);
  };

  const submitRequest = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const passSelect = event.currentTarget.elements.namedItem('passToken') as HTMLSelectElement | null;
    const passWindow = passSelect?.selectedOptions?.[0]?.textContent ?? (data.get('passWindow') as string);
    const payload = {
      type: data.get('jobType') as JobType,
      satellite: data.get('satellite') as string,
      ground_station: data.get('groundStation') as string,
      reservation_token: data.get('passToken') as string,
      pass_window: passWindow,
      parameter_set: data.get('parameterSet') as string,
      priority: data.get('priority') as string,
    };
    const res = await fetch(`${API_BASE}/jobs`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Job create failed');
    const created = await res.json();
    setJobs((prev) => [created, ...prev]);
    setShowModal(false);
  };

  const savePolicy = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const payload = {
      name: data.get('policyName') as string,
      mission: data.get('mission') as string,
      trigger: data.get('trigger') as string,
      parameter_set: data.get('parameterSet') as string,
      parameter_value: data.get('parameterValue') as string,
    };
    const res = await fetch(`${API_BASE}/policies`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error('Policy save failed');
    const created = await res.json();
    setPolicies((prev) => [created, ...prev]);
  };

  const viewContent = () => {
    switch (view) {
      case 'overview':
        return (
          <>
            <div className="stat-grid">
              <div className="stat-card"><p className="label">Satellites</p><p className="value">{overview.satellites ?? 0}</p></div>
              <div className="stat-card"><p className="label">Ground stations</p><p className="value">{overview.ground_stations ?? 0}</p></div>
              <div className="stat-card"><p className="label">Active keys</p><p className="value">{overview.active_keys ?? 0}</p></div>
              <div className="stat-card"><p className="label">Open alerts</p><p className="value">{overview.open_alerts ?? 0}</p></div>
            </div>
            <div className="two-col">
              <div className="panel">
                <h3>Upcoming passes</h3>
                <div className="plain-list">
                  {passes.slice(0, 3).map((item, index) => (
                    <div key={index} className="item"><span className="badge badge-key">{item.band}</span><span className="grow">{item.satellite} → {item.ground_station}</span><span className="time">{item.aos}</span></div>
                  ))}
                </div>
              </div>
              <div className="panel">
                <h3>Recent alerts</h3>
                <div className="plain-list">
                  {alerts.slice(0, 2).map((item) => (
                    <div key={item.id} className="item"><span className={item.severity === 'Warning' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.severity}</span><span className="grow">{item.device} — {item.condition}</span><span className="time">{item.opened}</span></div>
                  ))}
                </div>
              </div>
            </div>
          </>
        );
      case 'devices':
        return (
          <table>
            <thead><tr><th>Name</th><th>ID</th><th>Type</th><th>Mission</th><th>Status</th><th>Last contact</th></tr></thead>
            <tbody>{devices.map((device) => (
              <tr key={device.id}><td>{device.name}</td><td className="mono text-muted">{device.id}</td><td>{device.type}</td><td>{device.mission}</td><td><span className="badge badge-success">{device.status}</span></td><td className="text-muted">{device.last_contact}</td></tr>
            ))}</tbody>
          </table>
        );
      case 'passes':
        return (
          <table>
            <thead><tr><th>Satellite</th><th>Ground station</th><th>Band</th><th>AOS</th><th>LOS</th><th>Max elevation</th></tr></thead>
            <tbody>{passes.map((pass, index) => (
              <tr key={index}><td>{pass.satellite}</td><td>{pass.ground_station}</td><td><span className={pass.band === 'Passed' ? 'badge badge-neutral' : 'badge badge-key'}>{pass.band}</span></td><td>{pass.aos}</td><td>{pass.los}</td><td className="text-muted">{pass.elevation}</td></tr>
            ))}</tbody>
          </table>
        );
      case 'jobs':
        return (
          <table>
            <thead><tr><th>Job ID</th><th>Type</th><th>Route</th><th>State</th><th>Created</th></tr></thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.id} className="clickable" onClick={() => openJobDetail(job)}>
                  <td className="mono">{job.id}</td>
                  <td>{renderJobTypeBadge(job.type)}</td>
                  <td>{job.route}</td>
                  <td>{renderStateBadge(job.state)}</td>
                  <td className="text-muted">{job.created}</td>
                </tr>
              ))}
            </tbody>
          </table>
        );
      case 'keys':
        return (
          <table>
            <thead><tr><th>Key ID</th><th>Route</th><th>Parameter set</th><th>State</th><th>Created</th></tr></thead>
            <tbody>{keys.map((item) => (
              <tr key={item.id}><td className="mono">{item.id}</td><td>{item.route}</td><td className="mono text-muted">{item.parameter_set}</td><td><span className={item.state === 'Active' ? 'badge badge-success' : item.state === 'Superseded' ? 'badge badge-neutral' : 'badge badge-warning'}>{item.state}</span></td><td className="text-muted">{item.created}</td></tr>
            ))}</tbody>
          </table>
        );
      case 'telemetry':
        return (
          <div className="card-grid">
            {telemetry.map((item) => (
              <div key={item.name} className="health-card"><p className="name">{item.name}</p><div className="health-row"><span>Temperature</span><span>{item.temperature}</span></div><div className="health-row"><span>Tamper</span><span className="badge badge-success">{item.tamper}</span></div><div className="health-row"><span>Self-test</span><span className={item.self_test === 'Pass' ? 'badge badge-success' : 'badge badge-warning'}>{item.self_test}</span></div></div>
            ))}
          </div>
        );
      case 'config':
        return (
          <div className="two-col">
            <div className="panel">
              <h3>New policy</h3>
              <form onSubmit={savePolicy}>
                <label className="field">Policy name</label>
                <input type="text" name="policyName" placeholder="Aster constellation default" required />
                <label className="field">Mission</label>
                <select name="mission"><option>Aster constellation</option><option>Vela</option></select>
                <label className="field">Rekey trigger</label>
                <select name="trigger"><option value="pass">Pass-based</option><option value="time">Time-based</option><option value="volume">Volume-based</option><option value="ondemand">On-demand</option></select>
                <label className="field">Default KEM parameter set</label>
                <select name="parameterSet"><option>ML-KEM-1024</option><option>ML-KEM-768</option><option>ML-KEM-512</option></select>
                <label className="field">Rekey every</label>
                <select name="parameterValue"><option>Every pass</option><option>Every 2nd pass</option><option>12 hours</option><option>24 hours</option><option>72 hours</option><option>500 MB</option><option>1 GB</option><option>5 GB</option></select>
                <button className="btn-primary" type="submit" style={{ width: '100%', justifyContent: 'center', marginTop: '4px' }}>Save policy</button>
              </form>
            </div>
            <div className="panel">
              <h3>Existing policies</h3>
              <div className="plain-list">
                {policies.map((policy, index) => (
                  <div key={index} className="item"><span className="grow">{policy.name}</span><span className="time">{policy.trigger} · {policy.parameter_set}</span></div>
                ))}
              </div>
            </div>
          </div>
        );
      case 'alerts':
        return (
          <table>
            <thead><tr><th>Severity</th><th>Device</th><th>Condition</th><th>State</th><th>Opened</th><th></th></tr></thead>
            <tbody>{alerts.map((item) => (
              <tr key={item.id} id={`alert-${item.id}`}>
                <td><span className={item.severity === 'Warning' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.severity}</span></td>
                <td>{item.device}</td>
                <td className="text-muted">{item.condition}</td>
                <td><span className={item.state === 'Open' ? 'badge badge-warning' : 'badge badge-neutral'}>{item.state}</span></td>
                <td className="text-muted">{item.opened}</td>
                <td>{item.state === 'Open' ? <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12.5px' }} onClick={async () => {
                  await fetch(`${API_BASE}/alerts/${item.id}/acknowledge`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ acknowledged_by: 'ui' }) });
                  setAlerts((prev) => prev.map((alert) => alert.id === item.id ? { ...alert, state: 'Acknowledged' } : alert));
                }}>Acknowledge</button> : null}</td>
              </tr>
            ))}</tbody>
          </table>
        );
      case 'audit':
        return (
          <>
            <div className="panel" style={{ marginBottom: '20px' }}>
              <h3>Pending approvals</h3>
              <div className="plain-list"><div className="item"><span className="grow">Revoke KEY-8830</span><span className="time">1 of 2 approvals</span></div></div>
            </div>
            <table>
              <thead><tr><th>Event</th><th>Device</th><th>Actor</th><th>Time</th></tr></thead>
              <tbody>{audit.map((item, index) => (
                <tr key={index}><td className="mono">{item.event}</td><td>{item.device}</td><td className="text-muted">{item.actor}</td><td className="text-muted">{item.time}</td></tr>
              ))}</tbody>
            </table>
          </>
        );
      default:
        return null;
    }
  };

  useEffect(() => {
    const handler = (event: Event) => {
      if ((event as CustomEvent).type === 'closeModal') setShowModal(false);
    };
    window.addEventListener('closeModal', handler);
    return () => window.removeEventListener('closeModal', handler);
  }, []);

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><span>Groundlink</span></div>
        <nav>
          <div className="nav-label">Overview</div>
          {navItems.map((item) => (
            <button key={item.id} className={activeButtonClass(item.id)} onClick={() => setView(item.id)}>{item.label}</button>
          ))}
        </nav>
      </aside>
      <main className="main">
        <header className="topbar">
          <h1>{navItems.find((item) => item.id === view)?.label}</h1>
          <div className="topbar-actions">
            <div className="search"><input type="text" placeholder="Search devices, jobs, keys..." /></div>
            <button className="btn-primary" onClick={() => setShowModal(true)}>New request</button>
          </div>
        </header>
        <div className="content">{viewContent()}</div>
      </main>
      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            {selectedJob ? (
              <>
                <div className="modal-head"><h2 className="mono">{selectedJob.id}</h2><button className="modal-close" onClick={closeModal}>×</button></div>
                <div style={{ display: 'flex', gap: '6px', marginBottom: '16px' }}>
                  {renderJobTypeBadge(selectedJob.type)}{renderStateBadge(selectedJob.state)}
                </div>
                <p className="kv-val" style={{ marginTop: '-8px' }}>{selectedJob.route}</p>
                <p className="kv">Progress</p>
                <p className="kv-val">Scheduled · Dispatched · EK sent · CT received · Active</p>
                <p className="kv">Key material</p>
                <p className="kv-val" style={{ color: 'var(--text-muted)' }}>Not exposed via platform — resides only in HSM secure storage.</p>
              </>
            ) : (
              <>
                <div className="modal-head"><h2>New request</h2><button className="modal-close" onClick={closeModal}>×</button></div>
                <form onSubmit={submitRequest}>
                  <label className="field">Job type</label>
                  <div className="type-toggle">
                    <button type="button" className={requestType === 'key' ? 'on-key' : ''} onClick={() => setRequestType('key')}>Key exchange</button>
                    <button type="button" className={requestType === 'data' ? 'on-data' : ''} onClick={() => setRequestType('data')}>Data delivery</button>
                  </div>
                  <label className="field">Satellite</label>
                  <select name="satellite"><option>Aster-1</option><option>Aster-2</option><option>Vela-1</option></select>
                  <label className="field">Ground station</label>
                  <select name="groundStation"><option>GS-North</option><option>GS-South</option></select>
                  <label className="field">Pass</label>
                  <select name="passToken">
                    {passes.map((pass) => (
                      <option key={pass.reservation_token} value={pass.reservation_token}>
                        {`${pass.satellite} → ${pass.ground_station} · ${pass.band} · ${pass.aos} - ${pass.los}`}
                      </option>
                    ))}
                  </select>
                  {requestType === 'key' ? (
                    <>
                      <label className="field">KEM parameter set</label>
                      <select name="parameterSet"><option>ML-KEM-1024</option><option>ML-KEM-768</option><option>ML-KEM-512</option></select>
                      <input type="hidden" name="jobType" value="key" />
                    </>
                  ) : (
                    <>
                      <label className="field">Band</label>
                      <div className="fixed-field">X-band (fixed by design)</div>
                      <label className="field">Priority</label>
                      <select name="priority"><option>Normal</option><option>High</option></select>
                      <input type="hidden" name="jobType" value="data" />
                    </>
                  )}
                  <button className="btn-primary" type="submit" style={{ width: '100%', justifyContent: 'center', marginTop: '4px' }}>Create job</button>
                </form>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default App;
