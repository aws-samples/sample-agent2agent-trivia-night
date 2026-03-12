import React, { useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Container,
  Form,
  FormField,
  Header,
  Input,
  SpaceBetween,
} from '@cloudscape-design/components';
import AuthService from '../services/AuthService';

interface LoginFormProps {
  onLoginSuccess: () => void;
}

const LoginForm: React.FC<LoginFormProps> = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    setError('');
    setLoading(true);
    try {
      await AuthService.getInstance().signIn(username, password);
      onLoginSuccess();
    } catch (err: any) {
      setError(err.message || 'Sign in failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Box padding="xxxl">
      <Box margin={{ left: 'xxxl', right: 'xxxl' }}>
        <Container header={<Header variant="h1">LSS Workshop Platform</Header>}>
          <Form
            actions={
              <Button variant="primary" loading={loading} onClick={handleSubmit}>
                Sign in
              </Button>
            }
          >
            <SpaceBetween size="m">
              {error && <Alert type="error">{error}</Alert>}
              <FormField label="Username">
                <Input
                  value={username}
                  onChange={({ detail }) => setUsername(detail.value)}
                  placeholder="Enter your username"
                  onKeyDown={({ detail }: any) => {
                    if (detail.key === 'Enter') handleSubmit();
                  }}
                />
              </FormField>
              <FormField label="Password">
                <Input
                  type="password"
                  value={password}
                  onChange={({ detail }) => setPassword(detail.value)}
                  placeholder="Enter your password"
                  onKeyDown={({ detail }: any) => {
                    if (detail.key === 'Enter') handleSubmit();
                  }}
                />
              </FormField>
            </SpaceBetween>
          </Form>
        </Container>
      </Box>
    </Box>
  );
};

export default LoginForm;
