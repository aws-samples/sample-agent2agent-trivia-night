// Agent Edit Modal component for updating existing agents
import React, { useState, useEffect } from 'react';
import {
  Modal,
  Box,
  SpaceBetween,
  Button,
  FormField,
  Input,
  Textarea,
  Alert,
  Header,
  Container,
  Multiselect,
  Select,
  Toggle,
} from '@cloudscape-design/components';
import type { AgentCard } from '../types/AgentCard';
import { getApiClient } from '../services/apiClient';

interface AgentEditModalProps {
  visible: boolean;
  onDismiss: () => void;
  onSuccess?: () => void;
  agentId: string;
  initialAgentCard: AgentCard;
}

const AgentEditModal: React.FC<AgentEditModalProps> = ({
  visible,
  onDismiss,
  onSuccess,
  agentId,
  initialAgentCard,
}) => {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    version: '',
    url: '',
    skills: [] as string[],
    preferredTransport: '',
    streaming: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});

  // Initialize form data when modal opens
  useEffect(() => {
    if (visible && initialAgentCard) {
      setFormData({
        name: initialAgentCard.name || '',
        description: initialAgentCard.description || '',
        version: (initialAgentCard as any).version || '',
        url: initialAgentCard.url || '',
        skills: Array.isArray(initialAgentCard.skills)
          ? initialAgentCard.skills.map((skill) => skill.name || skill.id || '')
          : [],
        preferredTransport: (initialAgentCard as any).preferredTransport || 'JSONRPC',
        streaming: (initialAgentCard as any).capabilities?.streaming || false,
      });
      setValidationErrors({});
      setSubmitError(null);
    }
  }, [visible, initialAgentCard]);

  const transportOptions = [
    { label: 'JSONRPC', value: 'JSONRPC' },
    { label: 'HTTP', value: 'HTTP' },
    { label: 'WebSocket', value: 'WebSocket' },
  ];

  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (!formData.name.trim()) errors.name = 'Name is required';
    else if (formData.name.length > 100) errors.name = 'Name must be less than 100 characters';

    if (!formData.description.trim()) errors.description = 'Description is required';
    else if (formData.description.length > 1000) errors.description = 'Description must be less than 1000 characters';

    if (formData.version && !/^\d+\.\d+\.\d+(-[a-zA-Z0-9.-]+)?$/.test(formData.version)) {
      errors.version = 'Version must follow semantic versioning (e.g., 1.0.0)';
    }

    if (!formData.url.trim()) errors.url = 'URL is required';
    else if (!/^https?:\/\/[^\s/$.?#].[^\s]*$/.test(formData.url)) errors.url = 'URL must be a valid HTTP/HTTPS URL';

    setValidationErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async () => {
    if (!validateForm()) return;
    try {
      setSubmitting(true);
      setSubmitError(null);

      const updateData: Partial<AgentCard> = {
        name: formData.name,
        description: formData.description,
        url: formData.url,
      };
      if (formData.version !== ((initialAgentCard as any).version || '')) (updateData as any).version = formData.version;
      if (formData.preferredTransport !== ((initialAgentCard as any).preferredTransport || '')) {
        (updateData as any).preferredTransport = formData.preferredTransport;
      }

      const currentSkills = Array.isArray(initialAgentCard.skills)
        ? initialAgentCard.skills.map((s) => s.name || s.id || '')
        : [];
      if (JSON.stringify(formData.skills.sort()) !== JSON.stringify(currentSkills.sort())) {
        updateData.skills = formData.skills.map((skill, index) => ({
          id: `skill-${index}`,
          name: skill,
          description: skill,
          tags: [skill.toLowerCase()],
        }));
      }

      const currentStreaming = (initialAgentCard as any).capabilities?.streaming || false;
      if (formData.streaming !== currentStreaming) {
        (updateData as any).capabilities = {
          ...(initialAgentCard as any).capabilities,
          streaming: formData.streaming,
        };
      }

      if (Object.keys(updateData).length === 0) {
        setSubmitError('No changes detected');
        return;
      }

      const api = getApiClient();
      const success = await api.updateAgent(agentId, updateData);
      if (success) {
        onDismiss();
        onSuccess?.();
      } else {
        setSubmitError('Update operation failed');
      }
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : 'Failed to update agent');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDismiss = () => {
    setValidationErrors({});
    setSubmitError(null);
    setSubmitting(false);
    onDismiss();
  };

  const handleSkillsChange = (selectedOptions: readonly any[]) => {
    const skills = selectedOptions.map((option) => option.value || option.label);
    setFormData((prev) => ({ ...prev, skills }));
  };

  const skillsOptions = formData.skills.map((skill) => ({ label: skill, value: skill }));

  return (
    <Modal
      onDismiss={handleDismiss}
      visible={visible}
      closeAriaLabel="Close modal"
      size="large"
      footer={
        <Box float="right">
          <SpaceBetween direction="horizontal" size="xs">
            <Button variant="link" onClick={handleDismiss}>Cancel</Button>
            <Button variant="primary" onClick={handleSubmit} disabled={submitting} loading={submitting}>
              Update Agent
            </Button>
          </SpaceBetween>
        </Box>
      }
      header={`Edit Agent - ${initialAgentCard.name}`}
    >
      <SpaceBetween direction="vertical" size="l">
        {submitError && (
          <Alert type="error" header="Update Failed">{submitError}</Alert>
        )}

        <Container header={<Header variant="h2" description="Update agent information">Agent Details</Header>}>
          <SpaceBetween direction="vertical" size="m">
            <FormField label="Name" description="Agent display name" errorText={validationErrors.name}>
              <Input
                value={formData.name}
                onChange={({ detail }) => setFormData((prev) => ({ ...prev, name: detail.value }))}
                placeholder="Enter agent name"
              />
            </FormField>

            <FormField label="Description" description="Brief description of the agent" errorText={validationErrors.description}>
              <Textarea
                value={formData.description}
                onChange={({ detail }) => setFormData((prev) => ({ ...prev, description: detail.value }))}
                placeholder="Enter agent description"
                rows={3}
              />
            </FormField>

            <SpaceBetween direction="horizontal" size="m">
              <FormField label="Version" description="Semantic version (e.g., 1.0.0)" errorText={validationErrors.version}>
                <Input
                  value={formData.version}
                  onChange={({ detail }) => setFormData((prev) => ({ ...prev, version: detail.value }))}
                  placeholder="1.0.0"
                />
              </FormField>

              <FormField label="Preferred Transport" description="Communication protocol">
                <Select
                  selectedOption={transportOptions.find((opt) => opt.value === formData.preferredTransport) || null}
                  onChange={({ detail }) =>
                    setFormData((prev) => ({ ...prev, preferredTransport: detail.selectedOption.value || 'JSONRPC' }))
                  }
                  options={transportOptions}
                  placeholder="Select transport"
                />
              </FormField>
            </SpaceBetween>

            <FormField label="URL" description="Agent endpoint URL" errorText={validationErrors.url}>
              <Input
                value={formData.url}
                onChange={({ detail }) => setFormData((prev) => ({ ...prev, url: detail.value }))}
                placeholder="https://example.com/api"
              />
            </FormField>

            <FormField label="Skills" description="Agent capabilities (press Enter to add new skills)" errorText={validationErrors.skills}>
              <Multiselect
                selectedOptions={skillsOptions}
                onChange={({ detail }) => handleSkillsChange(detail.selectedOptions)}
                options={skillsOptions}
                placeholder="Type to add skills"
                tokenLimit={10}
                deselectAriaLabel={(option) => `Remove ${option.label}`}
                filteringType="auto"
                hideTokens={false}
                keepOpen={false}
              />
            </FormField>

            <FormField label="Capabilities" description="Agent streaming and other capabilities">
              <Toggle
                onChange={({ detail }) => setFormData((prev) => ({ ...prev, streaming: detail.checked }))}
                checked={formData.streaming}
              >
                Streaming support
              </Toggle>
            </FormField>
          </SpaceBetween>
        </Container>

        <Container header={<Header variant="h3">Update Information</Header>}>
          <SpaceBetween direction="vertical" size="xs">
            <div><strong>Agent ID:</strong> {agentId}</div>
            <div><strong>Current Version:</strong> {(initialAgentCard as any).version || 'N/A'}</div>
            <div><strong>Protocol Version:</strong> {(initialAgentCard as any).protocolVersion || 'N/A'}</div>
            <div style={{ fontSize: '0.875rem', color: '#666' }}>
              Only modified fields will be updated.
            </div>
          </SpaceBetween>
        </Container>
      </SpaceBetween>
    </Modal>
  );
};

export default AgentEditModal;
