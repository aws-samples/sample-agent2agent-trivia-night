import React, { useCallback, useEffect, useState } from 'react';
import {
  Box,
  Container,
  FormField,
  Header,
  Input,
  SpaceBetween,
} from '@cloudscape-design/components';
import { useSearchParams } from 'react-router-dom';
import type { AgentCard } from '../types/AgentCard';
import { getApiClient, ensureCredentials } from '../services/apiClient';
import AgentSelector from '../components/AgentSelector';
import AgentInfoHeader from '../components/AgentInfoHeader';
import ChatPanel, { type ChatMessage } from '../components/ChatPanel';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

let messageCounter = 0;
function nextId(): string {
  messageCounter += 1;
  return `msg-${Date.now()}-${messageCounter}`;
}

type AgentWithId = AgentCard & { agent_id: string };

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const ChatPage: React.FC = () => {
  const api = getApiClient();
  const [searchParams] = useSearchParams();

  /* ---- Agent selection state ---- */
  const [selectedAgent, setSelectedAgent] = useState<AgentWithId | null>(null);
  const [agents, setAgents] = useState<AgentWithId[] | undefined>(undefined);

  /* ---- Search state ---- */
  const [searchQuery, setSearchQuery] = useState('');
  const [searching, setSearching] = useState(false);

  /* ---- Chat state ---- */
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);

  /* ---- Credentials readiness ---- */
  const [credsReady, setCredsReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    ensureCredentials().then(() => {
      if (!cancelled) setCredsReady(true);
    });
    return () => { cancelled = true; };
  }, []);

  /* ---- Auto-select agent from query param ---- */
  useEffect(() => {
    if (!credsReady) return;
    const agentId = searchParams.get('agentId');
    if (agentId && !selectedAgent) {
      api.listAgents(100, 0).then((res) => {
        const found = res.items.find((a: any) => a.agent_id === agentId);
        if (found) {
          const withId = found as any;
          setSelectedAgent({ ...withId, agent_id: withId.agent_id } as AgentWithId);
        }
      }).catch(() => { /* ignore */ });
    }
  }, [searchParams, credsReady]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- Agent selection handler ---- */
  const handleAgentChange = useCallback((agent: AgentWithId) => {
    setSelectedAgent(agent);
    // Clear conversation when switching agents
    setMessages([]);
    setChatError(null);
  }, []);

  /* ---- Semantic search for agent discovery ---- */
  const handleSearch = useCallback(
    async (query: string) => {
      const trimmed = query.trim();
      if (!trimmed) {
        // Reset to full agent list
        setAgents(undefined);
        return;
      }
      setSearching(true);
      try {
        const results = await api.searchAgents(trimmed);
        const found: AgentWithId[] = results.map((r) => ({
          ...r.agent_card,
          agent_id: r.agent_id,
        }));
        setAgents(found);
      } catch {
        // On search failure, fall back to full list
        setAgents(undefined);
      } finally {
        setSearching(false);
      }
    },
    [api],
  );

  /* ---- Send message handler ---- */
  const handleSendMessage = useCallback(
    async (text: string) => {
      if (!selectedAgent) return;

      setChatError(null);

      // Add user message
      const userMsg: ChatMessage = {
        id: nextId(),
        role: 'user',
        content: text,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);

      // Call chat endpoint
      setChatLoading(true);
      try {
        const res = await api.chat(selectedAgent.agent_id, text);
        const agentMsg: ChatMessage = {
          id: nextId(),
          role: 'agent',
          content: res.response,
          timestamp: Date.now(),
        };
        setMessages((prev) => [...prev, agentMsg]);
      } catch (err: any) {
        setChatError(err.message ?? 'Failed to get a response from the agent.');
      } finally {
        setChatLoading(false);
      }
    },
    [api, selectedAgent],
  );

  /* ---- Render ---- */
  return (
    <SpaceBetween size="l">
      <Container header={<Header variant="h1">Chat Assistant</Header>}>
        <SpaceBetween size="m">
          {/* ---- Semantic search input ---- */}
          <FormField
            label="Discover Agents"
            description="Search agents by capability description"
          >
            <Input
              value={searchQuery}
              onChange={({ detail }) => {
                setSearchQuery(detail.value);
                if (!detail.value.trim()) {
                  setAgents(undefined);
                }
              }}
              onKeyDown={({ detail }: any) => {
                if (detail.key === 'Enter' || detail.keyCode === 13) {
                  handleSearch(searchQuery);
                }
              }}
              placeholder="e.g. life sciences trivia, drug interactions…"
              disabled={searching}
              type="search"
            />
          </FormField>

          {/* ---- Agent selector dropdown ---- */}
          <FormField label="Select Agent">
            <AgentSelector
              selectedAgentId={selectedAgent?.agent_id}
              onChange={handleAgentChange}
              agents={agents}
            />
          </FormField>
        </SpaceBetween>
      </Container>

      {/* ---- Agent info header ---- */}
      {selectedAgent && <AgentInfoHeader agent={selectedAgent} />}

      {/* ---- Chat panel ---- */}
      <Container
        disableContentPaddings
        header={
          selectedAgent ? (
            <Header variant="h2">
              Chat with {selectedAgent.name}
            </Header>
          ) : undefined
        }
      >
        {!selectedAgent ? (
          <Box textAlign="center" padding="xxl" color="text-status-inactive">
            Select an agent above to start chatting.
          </Box>
        ) : (
          <ChatPanel
            messages={messages}
            loading={chatLoading}
            error={chatError}
            onSendMessage={handleSendMessage}
            disabled={!selectedAgent}
            placeholder={`Message ${selectedAgent.name}…`}
          />
        )}
      </Container>
    </SpaceBetween>
  );
};

export default ChatPage;
