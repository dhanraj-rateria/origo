import { useQuery } from '@tanstack/react-query';
import { request } from '@/shared/api/client';

interface PolicySummary {
  name: string;
  mission: string;
  trigger: string;
  parameter_set: string;
  value: string;
}

export function PoliciesView() {
  const { data } = useQuery({
    queryKey: ['policies'],
    queryFn: () => request<PolicySummary[]>('/policies'),
  });

  return (
    <div className="two-col">
      <div className="panel">
        <h3>Existing policies</h3>
        <div className="plain-list">
          {(data ?? []).map((policy, index) => (
            <div key={`${policy.name}-${index}`} className="item"><span className="grow">{policy.name}</span><span className="time">{policy.trigger} · {policy.parameter_set}</span></div>
          ))}
        </div>
      </div>
    </div>
  );
}
