/**
 * Unit tests for AgentInfoHeader component.
 * Requirements: 5.3
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import AgentInfoHeader from '../AgentInfoHeader';

const agentWithSkills = {
  agent_id: 'agent-1',
  name: 'Life Science Agent',
  description: 'Expert in biology and chemistry topics',
  url: 'https://agent.example.com',
  version: '1.0.0',
  capabilities: { streaming: false },
  defaultInputModes: ['text/plain'],
  defaultOutputModes: ['text/plain'],
  skills: [
    { id: 'bio', name: 'Biology', description: 'Biology knowledge', tags: ['bio'] },
    { id: 'chem', name: 'Chemistry', description: 'Chemistry knowledge', tags: ['chem'] },
  ],
} as any;

const agentWithoutSkills = {
  agent_id: 'agent-2',
  name: 'Basic Agent',
  description: 'A simple agent with no skills',
  url: 'https://basic.example.com',
  version: '1.0.0',
  capabilities: {},
  defaultInputModes: ['text/plain'],
  defaultOutputModes: ['text/plain'],
  skills: [],
} as any;

describe('AgentInfoHeader', () => {
  it('renders nothing when agent is null', () => {
    const { container } = render(<AgentInfoHeader agent={null} />);
    expect(container.innerHTML).toBe('');
  });

  it('renders agent name and description', () => {
    const { container } = render(<AgentInfoHeader agent={agentWithSkills} />);
    const text = container.textContent ?? '';
    expect(text).toContain('Life Science Agent');
    expect(text).toContain('Expert in biology and chemistry topics');
  });

  it('renders skill badges when agent has skills', () => {
    const { container } = render(<AgentInfoHeader agent={agentWithSkills} />);
    const text = container.textContent ?? '';
    expect(text).toContain('Biology');
    expect(text).toContain('Chemistry');
  });

  it('shows "No skills listed" when agent has no skills', () => {
    const { container } = render(<AgentInfoHeader agent={agentWithoutSkills} />);
    const text = container.textContent ?? '';
    expect(text).toContain('No skills listed');
  });

  it('handles agent with missing optional fields gracefully', () => {
    const minimalAgent = {
      name: 'Minimal',
      description: undefined,
      url: 'https://min.example.com',
    };
    const { container } = render(<AgentInfoHeader agent={minimalAgent as any} />);
    const text = container.textContent ?? '';
    expect(text).toContain('Minimal');
  });
});
