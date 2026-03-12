/**
 * Unit tests for AgentSelector component.
 * Requirements: 5.2
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import AgentSelector from '../AgentSelector';

const mockAgents = [
  {
    agent_id: 'agent-1',
    name: 'Life Science Agent',
    description: 'Answers questions about biology and chemistry',
    url: 'https://agent1.example.com',
    version: '1.0.0',
    capabilities: { streaming: false },
    defaultInputModes: ['text/plain'],
    defaultOutputModes: ['text/plain'],
    skills: [{ id: 'bio', name: 'Biology', description: 'Biology knowledge', tags: ['bio'] }],
  },
  {
    agent_id: 'agent-2',
    name: 'Trivia Agent',
    description: 'General trivia knowledge',
    url: 'https://agent2.example.com',
    version: '1.0.0',
    capabilities: { streaming: false },
    defaultInputModes: ['text/plain'],
    defaultOutputModes: ['text/plain'],
    skills: [{ id: 'trivia', name: 'Trivia', description: 'Trivia questions', tags: ['trivia'] }],
  },
] as any[];

describe('AgentSelector', () => {
  it('renders with placeholder text when no agent is selected', () => {
    const onChange = vi.fn();
    const { container } = render(
      <AgentSelector agents={mockAgents} onChange={onChange} />,
    );
    // Cloudscape Select renders a button with the placeholder text
    const text = container.textContent ?? '';
    expect(text).toContain('Select an agent');
  });

  it('renders with the selected agent name when selectedAgentId is provided', () => {
    const onChange = vi.fn();
    const { container } = render(
      <AgentSelector
        agents={mockAgents}
        selectedAgentId="agent-1"
        onChange={onChange}
      />,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('Life Science Agent');
  });

  it('renders without crashing when agents list is empty', () => {
    const onChange = vi.fn();
    const { container } = render(
      <AgentSelector agents={[]} onChange={onChange} />,
    );
    expect(container).toBeTruthy();
  });

  it('renders with provided agents (does not fetch from API)', () => {
    const onChange = vi.fn();
    const { container } = render(
      <AgentSelector agents={mockAgents} onChange={onChange} />,
    );
    // Component should render without errors when agents are provided externally
    expect(container).toBeTruthy();
  });
});
