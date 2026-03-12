import React, { useEffect, useState } from 'react';
import { Select, SelectProps } from '@cloudscape-design/components';
import type { AgentCard } from '../types/AgentCard';
import { getApiClient, ensureCredentials } from '../services/apiClient';

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export interface AgentSelectorProps {
  /** Currently selected agent ID */
  selectedAgentId?: string;
  /** Called when the user picks a different agent */
  onChange: (agent: AgentCard & { agent_id: string }) => void;
  /** Optional pre-loaded agents list (skips API fetch when provided) */
  agents?: (AgentCard & { agent_id: string })[];
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const AgentSelector: React.FC<AgentSelectorProps> = ({
  selectedAgentId,
  onChange,
  agents: externalAgents,
}) => {
  const [agents, setAgents] = useState<(AgentCard & { agent_id: string })[]>(externalAgents ?? []);
  const [loading, setLoading] = useState(!externalAgents);
  const [error, setError] = useState('');

  /* ---- Load agents on mount when not provided externally ---- */
  useEffect(() => {
    if (externalAgents) {
      setAgents(externalAgents);
      setLoading(false);
      return;
    }

    let cancelled = false;
    const load = async () => {
      setLoading(true);
      try {
        await ensureCredentials();
        const api = getApiClient();
        const res = await api.listAgents(100, 0);
        if (!cancelled) {
          const items = res.items.map((a: any) => ({
            ...a,
            agent_id: a.agent_id ?? '',
          }));
          setAgents(items);
        }
      } catch (err: any) {
        if (!cancelled) setError(err.message ?? 'Failed to load agents');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, [externalAgents]);

  /* ---- Build select options ---- */
  const options: SelectProps.Option[] = agents.map((a) => ({
    value: a.agent_id,
    label: a.name ?? 'Unnamed Agent',
    description: a.description ? a.description.slice(0, 120) : undefined,
  }));

  const selectedOption =
    options.find((o) => o.value === selectedAgentId) ?? null;

  const handleChange: SelectProps['onChange'] = ({ detail }) => {
    const agent = agents.find((a) => a.agent_id === detail.selectedOption.value);
    if (agent) onChange(agent);
  };

  return (
    <Select
      selectedOption={selectedOption}
      onChange={handleChange}
      options={options}
      placeholder="Select an agent…"
      loadingText="Loading agents…"
      statusType={loading ? 'loading' : error ? 'error' : 'finished'}
      errorText={error}
      filteringType="auto"
      empty="No agents registered"
    />
  );
};

export default AgentSelector;
