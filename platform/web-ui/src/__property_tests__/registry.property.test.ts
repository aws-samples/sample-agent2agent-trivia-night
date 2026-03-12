/**
 * Property 16: Agent Table Displays All Required Columns
 *
 * For any list of agents returned from the API, the Agent Registry table
 * should render each agent with visible name, description, URL, skills,
 * and online status columns.
 *
 * Feature: lss-workshop-platform, Property 16: Agent Table Displays All Required Columns
 * **Validates: Requirements 6.1**
 */
import { describe, it, expect } from 'vitest';
import fc from 'fast-check';
import React from 'react';
import { render } from '@testing-library/react';
import { Table, StatusIndicator, TableProps } from '@cloudscape-design/components';

/* ------------------------------------------------------------------ */
/*  Mirror the AgentsPage row type and column definitions               */
/* ------------------------------------------------------------------ */

interface AgentRow {
  agent_id: string;
  name: string;
  description: string;
  url: string;
  skills: string;
  is_online: boolean;
}

const COLUMN_DEFINITIONS: TableProps.ColumnDefinition<AgentRow>[] = [
  { id: 'name', header: 'Name', cell: (item) => item.name },
  { id: 'description', header: 'Description', cell: (item) => item.description },
  { id: 'url', header: 'URL', cell: (item) => item.url },
  { id: 'skills', header: 'Skills', cell: (item) => item.skills },
  {
    id: 'status',
    header: 'Online Status',
    cell: (item) =>
      item.is_online
        ? React.createElement(StatusIndicator, { type: 'success' }, 'Online')
        : React.createElement(StatusIndicator, { type: 'stopped' }, 'Offline'),
  },
];

/* ------------------------------------------------------------------ */
/*  Arbitrary: random agent rows                                       */
/* ------------------------------------------------------------------ */

const agentRowArb: fc.Arbitrary<AgentRow> = fc.record({
  agent_id: fc.uuid(),
  name: fc.string({ minLength: 1, maxLength: 50 }),
  description: fc.string({ minLength: 1, maxLength: 100 }),
  url: fc.webUrl(),
  skills: fc.array(fc.string({ minLength: 1, maxLength: 20 }), { minLength: 0, maxLength: 5 })
    .map((s) => s.join(', ')),
  is_online: fc.boolean(),
});

const agentListArb = fc.array(agentRowArb, { minLength: 1, maxLength: 10 });

/* ------------------------------------------------------------------ */
/*  Property test                                                      */
/* ------------------------------------------------------------------ */

describe('Property 16: Agent Table Displays All Required Columns', () => {
  it('renders all required columns (name, description, url, skills, status) for every agent', () => {
    fc.assert(
      fc.property(agentListArb, (agents) => {
        const { container } = render(
          React.createElement(Table as any, {
            columnDefinitions: COLUMN_DEFINITIONS,
            items: agents,
            trackBy: 'agent_id',
          }),
        );

        // Verify all five column headers are present
        const headers = Array.from(container.querySelectorAll('th')).map(
          (th) => th.textContent?.trim() ?? '',
        );
        expect(headers).toContain('Name');
        expect(headers).toContain('Description');
        expect(headers).toContain('URL');
        expect(headers).toContain('Skills');
        expect(headers).toContain('Online Status');

        // Verify each agent's data appears in the table body
        const rows = container.querySelectorAll('tbody tr');
        expect(rows.length).toBe(agents.length);

        rows.forEach((row, idx) => {
          const cells = row.querySelectorAll('td');
          // 5 columns
          expect(cells.length).toBe(5);

          const agent = agents[idx];
          expect(cells[0].textContent).toContain(agent.name);
          expect(cells[1].textContent).toContain(agent.description);
          expect(cells[2].textContent).toContain(agent.url);
          expect(cells[3].textContent).toContain(agent.skills);
          // Status column should contain either "Online" or "Offline"
          const statusText = cells[4].textContent ?? '';
          if (agent.is_online) {
            expect(statusText).toContain('Online');
          } else {
            expect(statusText).toContain('Offline');
          }
        });
      }),
      { numRuns: 100 },
    );
  });
});
