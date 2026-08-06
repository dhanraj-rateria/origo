import { createBrowserRouter, Navigate } from 'react-router-dom';
import { OverviewView } from '@/features/overview/OverviewView';
import { DevicesView } from '@/features/devices/DevicesView';
import { PassesView } from '@/features/passes/PassesView';
import { JobsView } from '@/features/jobs/JobsView';
import { KeysView } from '@/features/keys/KeysView';
import { TelemetryView } from '@/features/telemetry/TelemetryView';
import { PoliciesView } from '@/features/policies/PoliciesView';
import { AlertsView } from '@/features/alerts/AlertsView';
import { AuditView } from '@/features/audit/AuditView';
import { AppShell } from './App';

export const router = createBrowserRouter([
  {
    path: '/',
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/overview" replace /> },
      { path: 'overview', element: <OverviewView /> },
      { path: 'devices', element: <DevicesView /> },
      { path: 'passes', element: <PassesView /> },
      { path: 'jobs', element: <JobsView /> },
      { path: 'keys', element: <KeysView /> },
      { path: 'telemetry', element: <TelemetryView /> },
      { path: 'policies', element: <PoliciesView /> },
      { path: 'alerts', element: <AlertsView /> },
      { path: 'audit', element: <AuditView /> },
    ],
  },
]);
