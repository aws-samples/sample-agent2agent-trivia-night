import React from 'react';
import { Badge, Box, Container, Header, SpaceBetween } from '@cloudscape-design/components';
import type { AgentCard } from '../types/AgentCard';

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

export interface AgentInfoHeaderProps {
  /** The currently selected agent (null when nothing is selected) */
  agent: (AgentCard & { agent_id?: string }) | null;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const AgentInfoHeader: React.FC<AgentInfoHeaderProps> = ({ agent }) => {
  if (!agent) return null;

  const skills: { id?: string; name?: string; description?: string }[] =
    Array.isArray((agent as any).skills) ? (agent as any).skills : [];

  return (
    <Container
      header={
        <Header variant="h2" description={agent.description ?? ''}>
          {agent.name ?? 'Unknown Agent'}
        </Header>
      }
    >
      {skills.length > 0 && (
        <SpaceBetween direction="horizontal" size="xs">
          {skills.map((skill, idx) => (
            <Badge key={skill.id ?? skill.name ?? idx} color="blue">
              {skill.name ?? skill.id ?? 'skill'}
            </Badge>
          ))}
        </SpaceBetween>
      )}
      {skills.length === 0 && (
        <Box color="text-status-inactive" variant="small">
          No skills listed
        </Box>
      )}
    </Container>
  );
};

export default AgentInfoHeader;
