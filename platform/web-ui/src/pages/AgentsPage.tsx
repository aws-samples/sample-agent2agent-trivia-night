// Agents page - full agent registry with search, filtering, JSON viewer, edit/delete
import React, { useCallback, useEffect, useState } from 'react';
import {
  Badge,
  Box,
  Button,
  Cards,
  CollectionPreferences,
  Container,
  ContentLayout,
  Header,
  Link,
  Modal,
  Pagination,
  PropertyFilter,
  SegmentedControl,
  SpaceBetween,
  Table,
  Textarea,
  TextFilter,
} from '@cloudscape-design/components';
import { useNavigate } from 'react-router-dom';
import type { AgentCard, Agent } from '../types/AgentCard';
import { getApiClient, ensureCredentials } from '../services/apiClient';
import AgentEditModal from '../components/AgentEditModal';

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function relativeTime(dateStr: string): string {
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 60000);
  if (diff < 1) return 'Just now';
  if (diff < 60) return `${diff} minutes ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)} hours ago`;
  return new Date(dateStr).toLocaleDateString();
}

/* ------------------------------------------------------------------ */
/*  Property filter config                                             */
/* ------------------------------------------------------------------ */

const FILTERING_PROPERTIES = [
  {
    key: 'name',
    operators: [':', '!:', '=', '!='] as const,
    propertyLabel: 'Agent name',
    groupValuesLabel: 'Agent name values',
  },
  {
    key: 'skills',
    operators: [':', '!:', '=', '!='] as const,
    propertyLabel: 'Skills',
    groupValuesLabel: 'Skill values',
  },
  {
    key: 'version',
    operators: [':', '!:', '=', '!='] as const,
    propertyLabel: 'Version',
    groupValuesLabel: 'Version values',
  },
];

const PROPERTY_FILTER_I18N = {
  filteringAriaLabel: 'Filter agents by properties',
  dismissAriaLabel: 'Dismiss',
  filteringPlaceholder: 'Filter agents by properties',
  groupValuesText: 'Values',
  groupPropertiesText: 'Properties',
  operatorsText: 'Operators',
  operationAndText: 'and',
  operationOrText: 'or',
  operatorLessText: 'Less than',
  operatorLessOrEqualText: 'Less than or equal',
  operatorGreaterText: 'Greater than',
  operatorGreaterOrEqualText: 'Greater than or equal',
  operatorContainsText: 'Contains',
  operatorDoesNotContainText: 'Does not contain',
  operatorEqualsText: 'Equals',
  operatorDoesNotEqualText: 'Does not equal',
  editTokenHeader: 'Edit filter',
  propertyText: 'Property',
  operatorText: 'Operator',
  valueText: 'Value',
  cancelActionText: 'Cancel',
  applyActionText: 'Apply',
  allPropertiesLabel: 'All properties',
  tokenLimitShowMore: 'Show more',
  tokenLimitShowFewer: 'Show fewer',
  clearFiltersText: 'Clear filters',
  removeTokenButtonAriaLabel: (token: any) => `Remove token ${token.propertyKey} ${token.operator} ${token.value}`,
  enteredTextLabel: (text: string) => `Use: "${text}"`,
};

/* ------------------------------------------------------------------ */
/*  Property filter logic                                              */
/* ------------------------------------------------------------------ */

function applyPropertyFilters(agents: Agent[], filters: any): Agent[] {
  if (!filters.tokens || filters.tokens.length === 0) return agents;

  return agents.filter((agent) => {
    const results = filters.tokens.map((token: any) => {
      const { propertyKey, operator, value } = token;
      const searchVal = value.toLowerCase();

      if (propertyKey === 'name') {
        const name = (agent.agent_card.name ?? '').toLowerCase();
        if (operator === ':') return name.includes(searchVal);
        if (operator === '!:') return !name.includes(searchVal);
        if (operator === '=') return name === searchVal;
        if (operator === '!=') return name !== searchVal;
        return name.includes(searchVal);
      }

      if (propertyKey === 'skills') {
        const skills = agent.agent_card.skills ?? [];
        const match = skills.some(
          (s) =>
            s.name?.toLowerCase().includes(searchVal) ||
            s.description?.toLowerCase().includes(searchVal),
        );
        if (operator === ':') return match;
        if (operator === '!:') return !match;
        if (operator === '=') return skills.some((s) => s.name?.toLowerCase() === searchVal);
        if (operator === '!=') return !skills.some((s) => s.name?.toLowerCase() === searchVal);
        return match;
      }

      if (propertyKey === 'version') {
        const version = ((agent.agent_card as any).version ?? '').toLowerCase();
        if (operator === ':') return version.includes(searchVal);
        if (operator === '!:') return !version.includes(searchVal);
        if (operator === '=') return version === searchVal;
        if (operator === '!=') return version !== searchVal;
        return version.includes(searchVal);
      }

      return true;
    });

    return filters.operation === 'and' ? results.every(Boolean) : results.some(Boolean);
  });
}

/* ------------------------------------------------------------------ */
/*  Default preferences                                                */
/* ------------------------------------------------------------------ */

const DEFAULT_PREFERENCES = {
  pageSize: 20,
  visibleContent: ['name', 'version', 'skills', 'updated_at', 'actions'],
  wrapLines: true,
  stripedRows: false,
  contentDensity: 'comfortable' as const,
};

function loadPreferences() {
  try {
    const stored = localStorage.getItem('agent-registry-table-preferences');
    if (stored) {
      const parsed = JSON.parse(stored);
      // Ensure actions is always visible
      if (!parsed.visibleContent?.includes('actions')) {
        parsed.visibleContent = [...(parsed.visibleContent || []), 'actions'];
      }
      return { ...DEFAULT_PREFERENCES, ...parsed };
    }
  } catch { /* use defaults */ }
  return DEFAULT_PREFERENCES;
}


/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const AgentsPage: React.FC = () => {
  const api = getApiClient();
  const navigate = useNavigate();

  /* ---- Data state ---- */
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalItems, setTotalItems] = useState(0);
  const [selectedItems, setSelectedItems] = useState<Agent[]>([]);

  /* ---- Filter state ---- */
  const [filteringText, setFilteringText] = useState('');
  const [propertyFilters, setPropertyFilters] = useState<any>({ tokens: [], operation: 'and' });

  /* ---- Pagination state ---- */
  const [currentPageIndex, setCurrentPageIndex] = useState(1);
  const [preferences, setPreferences] = useState(loadPreferences);

  /* ---- JSON modal state ---- */
  const [jsonModalVisible, setJsonModalVisible] = useState(false);
  const [selectedAgentCard, setSelectedAgentCard] = useState<Agent | null>(null);

  /* ---- View mode ---- */
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('grid');

  /* ---- Edit modal state ---- */
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [editingAgent, setEditingAgent] = useState<Agent | null>(null);

  /* ---- Delete state ---- */
  const [deleteLoading, setDeleteLoading] = useState<string | null>(null);

  const pageSize = preferences.pageSize;

  /* ---- Load agents ---- */
  const loadAgents = useCallback(
    async (page: number = currentPageIndex, searchQuery: string = filteringText) => {
      setLoading(true);
      setError(null);
      try {
        let transformed: Agent[] = [];
        let total = 0;

        if (searchQuery.trim()) {
          const results = await api.searchAgents(searchQuery, undefined, 30);
          transformed = results.map((r, i) => ({
            agent_id: r.agent_id || `search-${i + 1}`,
            agent_card: r.agent_card,
            is_online: false,
            updated_at: (r as any).updated_at || new Date().toISOString(),
          }));
          total = transformed.length;
        } else {
          const offset = (page - 1) * pageSize;
          const res = await api.listAgents(pageSize, offset);
          transformed = res.items.map((item, i) => {
            const withId = item as any;
            const id = withId.agent_id || `agent-${offset + i + 1}`;
            const updatedAt = withId.updated_at || new Date().toISOString();
            const { agent_id: _aid, updated_at: _upd, is_online: _on, ...cleanCard } = withId;
            return {
              agent_id: id,
              agent_card: cleanCard as AgentCard,
              is_online: withId.is_online ?? false,
              updated_at: updatedAt,
            };
          });
          total = res.total;
        }

        setAgents(transformed);
        setTotalItems(total);
      } catch (err: any) {
        setError(err.message ?? 'Failed to load agents');
        setAgents([]);
        setTotalItems(0);
      } finally {
        setLoading(false);
      }
    },
    [api, currentPageIndex, pageSize, filteringText],
  );

  const refresh = useCallback(() => loadAgents(currentPageIndex), [loadAgents, currentPageIndex]);

  /* ---- Initial load ---- */
  useEffect(() => {
    ensureCredentials().then(() => loadAgents());
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- Debounced search ---- */
  useEffect(() => {
    const id = setTimeout(() => loadAgents(1, filteringText), 300);
    return () => clearTimeout(id);
  }, [filteringText]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---- Handlers ---- */
  const handleFilteringTextChange = (text: string) => {
    setFilteringText(text);
    setCurrentPageIndex(1);
  };

  const handlePropertyFiltersChange = (detail: any) => {
    setPropertyFilters(detail);
    setCurrentPageIndex(1);
  };

  const handlePaginationChange = (detail: any) => {
    const newPage = detail.currentPageIndex;
    setCurrentPageIndex(newPage);
    if (!filteringText.trim()) loadAgents(newPage, filteringText);
  };

  const handleViewJson = (agent: Agent) => {
    setSelectedAgentCard(agent);
    setJsonModalVisible(true);
  };

  const handleCopyJson = async (agent: Agent) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(agent.agent_card, null, 2));
    } catch {
      const ta = document.createElement('textarea');
      ta.value = JSON.stringify(agent.agent_card, null, 2);
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
    }
  };

  const handleEditAgent = (agent: Agent) => {
    setEditingAgent(agent);
    setEditModalVisible(true);
  };

  const handleEditSuccess = () => refresh();

  const handleDeleteAgent = async (agent: Agent) => {
    if (!window.confirm(`Are you sure you want to delete agent "${agent.agent_card.name}"?`)) return;
    try {
      setDeleteLoading(agent.agent_id);
      await api.deleteAgent(agent.agent_id);
      refresh();
    } catch (err: any) {
      setError(`Failed to delete agent: ${err.message ?? 'Unknown error'}`);
    } finally {
      setDeleteLoading(null);
    }
  };

  /* ---- Apply property filters + paginate ---- */
  const filtered = applyPropertyFilters(agents, propertyFilters);
  const filteredTotal =
    propertyFilters.tokens?.length > 0 ? filtered.length : totalItems;
  const displayAgents =
    filteringText.trim() || propertyFilters.tokens?.length > 0
      ? filtered.slice((currentPageIndex - 1) * pageSize, currentPageIndex * pageSize)
      : filtered;
  const totalPages = Math.ceil(filteredTotal / pageSize);


  /* ---- Column definitions ---- */
  const columnDefinitions = [
    {
      id: 'name',
      header: 'Agent Name',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', flexDirection: 'column' as const, justifyContent: 'center' }}>
          <div style={{ fontWeight: 'bold', marginBottom: '4px' }}>{item.agent_card.name}</div>
          <div style={{ fontSize: '0.875rem', color: '#666', lineHeight: '1.4', wordWrap: 'break-word' as const, maxWidth: '300px' }}>
            {item.agent_card.description}
          </div>
        </div>
      ),
      sortingField: 'agent_card.name',
      minWidth: 250,
    },
    {
      id: 'version',
      header: 'Version',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', alignItems: 'center' }}>
          {(item.agent_card as any).version ?? 'N/A'}
        </div>
      ),
      sortingField: 'agent_card.version',
      minWidth: 100,
    },
    {
      id: 'skills',
      header: 'Skills',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', alignItems: 'center' }}>
          <SpaceBetween direction="horizontal" size="xs">
            {(item.agent_card.skills || []).slice(0, 4).map((skill, i) => (
              <Badge key={i} color="blue">{skill.name}</Badge>
            ))}
            {(item.agent_card.skills || []).length > 4 && (
              <Badge color="grey">+{(item.agent_card.skills || []).length - 4} more</Badge>
            )}
          </SpaceBetween>
        </div>
      ),
      minWidth: 250,
    },
    {
      id: 'updated_at',
      header: 'Last Updated',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', alignItems: 'center' }}>
          {relativeTime(item.updated_at)}
        </div>
      ),
      sortingField: 'updated_at',
      minWidth: 150,
    },
    {
      id: 'agent_id',
      header: 'Agent ID',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', alignItems: 'center' }}>
          <Box fontSize="body-s" color="text-body-secondary">{item.agent_id}</Box>
        </div>
      ),
      minWidth: 200,
    },
    {
      id: 'actions',
      header: 'Actions',
      cell: (item: Agent) => (
        <div style={{ minHeight: '60px', display: 'flex', alignItems: 'center' }}>
          <SpaceBetween direction="horizontal" size="xs">
            <Button onClick={() => navigate(`/chat?agentId=${item.agent_id}`)} iconName="contact" variant="normal">Chat</Button>
            <Button onClick={() => handleViewJson(item)} iconName="file-open" variant="normal">View JSON</Button>
            <Button onClick={() => handleCopyJson(item)} iconName="copy" variant="normal">Copy</Button>
            <Button onClick={() => handleEditAgent(item)} iconName="edit" variant="normal">Edit</Button>
            <Button onClick={() => handleDeleteAgent(item)} iconName="remove" variant="normal" loading={deleteLoading === item.agent_id}>Delete</Button>
          </SpaceBetween>
        </div>
      ),
      minWidth: 280,
    },
  ];

  /* ---- Preferences handling ---- */
  const handlePreferencesChange = (detail: any) => {
    const prefs = {
      ...detail.preferences,
      visibleContent: detail.preferences.visibleContent.filter((id: string) => id !== 'actions'),
    };
    try {
      localStorage.setItem('agent-registry-table-preferences', JSON.stringify(prefs));
    } catch { /* ignore */ }
    // Re-add actions for display
    setPreferences({ ...detail.preferences, visibleContent: [...prefs.visibleContent, 'actions'] });
  };

  const visibleColumns = columnDefinitions.filter(
    (col) => preferences.visibleContent.includes(col.id) || col.id === 'actions',
  );


  /* ---- Render ---- */

  const filterSection = (
    <SpaceBetween direction="vertical" size="xs">
      <TextFilter
        filteringText={filteringText}
        onChange={({ detail }) => handleFilteringTextChange(detail.filteringText)}
        filteringPlaceholder="Search agents by name, description, or skills (semantic search)..."
        filteringAriaLabel="Filter agents"
      />
      <PropertyFilter
        query={propertyFilters}
        onChange={({ detail }) => handlePropertyFiltersChange(detail)}
        filteringProperties={FILTERING_PROPERTIES}
        filteringPlaceholder="Filter agents by properties"
        filteringAriaLabel="Filter agents by properties"
        expandToViewport
        i18nStrings={PROPERTY_FILTER_I18N}
      />
    </SpaceBetween>
  );

  const headerSection = (
    <Header
      counter={`(${filteredTotal})`}
      actions={
        <SpaceBetween direction="horizontal" size="xs">
          <SegmentedControl
            selectedId={viewMode}
            onChange={({ detail }) => setViewMode(detail.selectedId as 'table' | 'grid')}
            options={[
              { id: 'table', iconName: 'view-horizontal' },
              { id: 'grid', iconName: 'view-full' },
            ]}
          />
          <Button onClick={refresh} iconName="refresh">Refresh</Button>
          <Button variant="primary" onClick={() => navigate('/register')}>Register Agent</Button>
        </SpaceBetween>
      }
    >
      Agents
    </Header>
  );

  const emptyState = (
    <Box textAlign="center" color="inherit">
      <b>No agents found</b>
      <Box padding={{ bottom: 's' }} variant="p" color="inherit">
        {error ? 'There was an error loading agents.' : 'No agents match the current filters.'}
      </Box>
      <Button onClick={() => navigate('/register')}>Register your first agent</Button>
    </Box>
  );

  const paginationSection = (
    <Pagination
      currentPageIndex={currentPageIndex}
      pagesCount={totalPages}
      onChange={({ detail }) => handlePaginationChange(detail)}
    />
  );

  return (
    <ContentLayout
      header={
        <Header
          variant="h1"
          description="View and manage registered agents. Search by name, description, or skills."
        >
          Agent Registry
        </Header>
      }
    >
      {viewMode === 'table' ? (
      <Table
        columnDefinitions={visibleColumns}
        items={displayAgents}
        loading={loading}
        loadingText="Loading agents..."
        selectedItems={selectedItems}
        onSelectionChange={({ detail }) => setSelectedItems(detail.selectedItems)}
        selectionType="multi"
        trackBy="agent_id"
        wrapLines={preferences.wrapLines}
        stripedRows={preferences.stripedRows}
        contentDensity={preferences.contentDensity}
        empty={emptyState}
        filter={filterSection}
        header={headerSection}
        pagination={paginationSection}
        preferences={
          <CollectionPreferences
            title="Preferences"
            confirmLabel="Confirm"
            cancelLabel="Cancel"
            preferences={{
              ...preferences,
              visibleContent: preferences.visibleContent.filter((id: string) => id !== 'actions'),
            }}
            onConfirm={({ detail }) => handlePreferencesChange(detail)}
            pageSizePreference={{
              title: 'Page size',
              options: [
                { value: 10, label: '10 agents' },
                { value: 20, label: '20 agents' },
                { value: 50, label: '50 agents' },
                { value: 100, label: '100 agents' },
              ],
            }}
            visibleContentPreference={{
              title: 'Select visible columns',
              options: [
                {
                  label: 'Agent properties',
                  options: columnDefinitions
                    .filter((col) => col.id !== 'actions')
                    .map((col) => ({
                      id: col.id,
                      label: col.header as string,
                      editable: col.id !== 'name',
                    })),
                },
              ],
            }}
            wrapLinesPreference={{
              label: 'Wrap lines',
              description: 'Check to see all the text and wrap the lines',
            }}
            stripedRowsPreference={{
              label: 'Striped rows',
              description: 'Check to add alternating shaded rows',
            }}
            contentDensityPreference={{
              label: 'Compact mode',
              description: 'Check to display content in a denser, more compact mode',
            }}
          />
        }
      />
      ) : (
      <Cards
        cardDefinition={{
          header: (item: Agent) => (
            <Link fontSize="heading-m" onFollow={(e) => { e.preventDefault(); handleViewJson(item); }}>
              {item.agent_card.name}
            </Link>
          ),
          sections: [
            {
              id: 'description',
              header: 'Description',
              content: (item: Agent) => item.agent_card.description,
            },
            {
              id: 'skills',
              header: 'Skills',
              content: (item: Agent) => (
                <SpaceBetween direction="horizontal" size="xs">
                  {(item.agent_card.skills || []).slice(0, 6).map((skill, i) => (
                    <Badge key={i} color="blue">{skill.name}</Badge>
                  ))}
                  {(item.agent_card.skills || []).length > 6 && (
                    <Badge color="grey">+{(item.agent_card.skills || []).length - 6} more</Badge>
                  )}
                </SpaceBetween>
              ),
            },
            {
              id: 'meta',
              header: 'Details',
              content: (item: Agent) => (
                <SpaceBetween direction="vertical" size="xxxs">
                  <div>Version: {(item.agent_card as any).version ?? 'N/A'}</div>
                  <div>Updated: {relativeTime(item.updated_at)}</div>
                </SpaceBetween>
              ),
            },
            {
              id: 'actions',
              content: (item: Agent) => (
                <SpaceBetween direction="horizontal" size="xs">
                  <Button onClick={() => navigate(`/chat?agentId=${item.agent_id}`)} iconName="contact" variant="inline-link">Chat</Button>
                  <Button onClick={() => handleViewJson(item)} iconName="file-open" variant="inline-link">JSON</Button>
                  <Button onClick={() => handleCopyJson(item)} iconName="copy" variant="inline-link">Copy</Button>
                  <Button onClick={() => handleEditAgent(item)} iconName="edit" variant="inline-link">Edit</Button>
                  <Button onClick={() => handleDeleteAgent(item)} iconName="remove" variant="inline-link"
                    loading={deleteLoading === item.agent_id}>Delete</Button>
                </SpaceBetween>
              ),
            },
          ],
        }}
        cardsPerRow={[{ cards: 1 }, { minWidth: 600, cards: 2 }, { minWidth: 1000, cards: 3 }]}
        items={displayAgents}
        loading={loading}
        loadingText="Loading agents..."
        trackBy="agent_id"
        empty={emptyState}
        filter={filterSection}
        header={headerSection}
        pagination={paginationSection}
      />
      )}

      {/* JSON Modal */}
      <Modal
        onDismiss={() => setJsonModalVisible(false)}
        visible={jsonModalVisible}
        size="large"
        header={selectedAgentCard ? `Agent Card JSON - ${selectedAgentCard.agent_card.name}` : 'Agent Card JSON'}
        footer={
          <Box float="right">
            <SpaceBetween direction="horizontal" size="xs">
              <Button onClick={() => selectedAgentCard && handleCopyJson(selectedAgentCard)} iconName="copy">
                Copy to Clipboard
              </Button>
              <Button variant="primary" onClick={() => setJsonModalVisible(false)}>Close</Button>
            </SpaceBetween>
          </Box>
        }
      >
        {selectedAgentCard && (
          <Container>
            <Textarea
              value={JSON.stringify(selectedAgentCard.agent_card, null, 2)}
              readOnly
              rows={20}
              spellcheck={false}
              ariaLabel="Agent card JSON"
            />
          </Container>
        )}
      </Modal>

      {/* Edit Modal */}
      {editingAgent && (
        <AgentEditModal
          visible={editModalVisible}
          onDismiss={() => setEditModalVisible(false)}
          onSuccess={handleEditSuccess}
          agentId={editingAgent.agent_id}
          initialAgentCard={editingAgent.agent_card}
        />
      )}
    </ContentLayout>
  );
};

export default AgentsPage;
