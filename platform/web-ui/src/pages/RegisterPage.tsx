// Register page - agent registration with JSON AgentCard input
import React, { useState } from 'react';
import {
  ContentLayout,
  Header,
  SpaceBetween,
  Container,
  Button,
  Alert,
  Box,
  StatusIndicator,
} from '@cloudscape-design/components';
import { useNavigate } from 'react-router-dom';
import AgentRegistrationModal from '../components/AgentRegistrationModal';

const RegisterPage: React.FC = () => {
  const navigate = useNavigate();
  const [modalVisible, setModalVisible] = useState(false);
  const [registrationSuccess, setRegistrationSuccess] = useState<string | null>(null);

  const handleOpenModal = () => {
    setModalVisible(true);
    setRegistrationSuccess(null);
  };

  const handleCloseModal = () => {
    setModalVisible(false);
  };

  const handleRegistrationSuccess = (agentId: string) => {
    setRegistrationSuccess(agentId);
    setTimeout(() => {
      navigate('/agents');
    }, 3000);
  };

  return (
    <>
      <ContentLayout
        header={
          <Header
            variant="h1"
            description="Register new agents by uploading AgentCard JSON files or pasting JSON content directly"
            actions={
              <Button variant="primary" onClick={handleOpenModal}>
                Register New Agent
              </Button>
            }
          >
            Agent Registration
          </Header>
        }
      >
        <SpaceBetween direction="vertical" size="l">
          {registrationSuccess && (
            <Alert
              type="success"
              header="Agent Registered Successfully"
              action={
                <Button onClick={() => navigate('/agents')}>
                  View All Agents
                </Button>
              }
            >
              Your agent has been registered with ID: <strong>{registrationSuccess}</strong>
              <br />
              You will be redirected to the agents page in a few seconds.
            </Alert>
          )}

          <Container header={<Header variant="h2">Getting Started</Header>}>
            <SpaceBetween direction="vertical" size="m">
              <Box>
                <h3>What is an AgentCard?</h3>
                <p>
                  An AgentCard is a JSON document that describes an AI agent following the A2A (Agent-to-Agent) protocol.
                  It contains metadata about the agent including its capabilities, skills, and communication preferences.
                </p>
              </Box>

              <Box>
                <h3>Registration Process</h3>
                <ol>
                  <li>Click "Register New Agent" to open the registration modal</li>
                  <li>Upload a JSON file or paste your AgentCard JSON content</li>
                  <li>The system will validate the format and required fields</li>
                  <li>Submit the form to register your agent</li>
                  <li>Your agent will be available for discovery immediately</li>
                </ol>
              </Box>

              <Box>
                <h3>AgentCard Requirements</h3>
                <p>Your AgentCard JSON must include:</p>
                <ul>
                  <li><strong>Basic Info:</strong> name, description, url</li>
                  <li><strong>Skills:</strong> Array of skill objects with id, name, description</li>
                </ul>
                <p>Recommended fields:</p>
                <ul>
                  <li><strong>Protocol:</strong> version, protocolVersion, preferredTransport</li>
                  <li><strong>Capabilities:</strong> Object with streaming and pushNotifications booleans</li>
                  <li><strong>Communication:</strong> defaultInputModes and defaultOutputModes arrays</li>
                </ul>
              </Box>

              <Box>
                <h3>Need Help?</h3>
                <p>
                  Use the "Load Sample" button in the registration modal to see a complete example of a valid AgentCard.
                  The system will validate your JSON and provide specific error messages if any required fields are missing.
                </p>
              </Box>
            </SpaceBetween>
          </Container>

          <Container header={<Header variant="h2">Current Status</Header>}>
            <SpaceBetween direction="vertical" size="s">
              <Box>
                <StatusIndicator type="success">Agent Registry Service is operational</StatusIndicator>
              </Box>
              <Box>
                <StatusIndicator type="success">JSON validation is active</StatusIndicator>
              </Box>
              <Box>
                <StatusIndicator type="success">A2A protocol compliance checking enabled</StatusIndicator>
              </Box>
            </SpaceBetween>
          </Container>
        </SpaceBetween>
      </ContentLayout>

      <AgentRegistrationModal
        visible={modalVisible}
        onDismiss={handleCloseModal}
        onSuccess={handleRegistrationSuccess}
      />
    </>
  );
};

export default RegisterPage;
