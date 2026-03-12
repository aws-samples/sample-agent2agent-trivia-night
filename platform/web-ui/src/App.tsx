import React, { useEffect, useState } from 'react';
import '@cloudscape-design/global-styles/index.css';
import { applyMode, Mode } from '@cloudscape-design/global-styles';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Box, Container, Spinner } from '@cloudscape-design/components';

import AuthService from './services/AuthService';
import LoginForm from './components/LoginForm';
import Layout from './components/Layout';
import ChatPage from './pages/ChatPage';
import AgentsPage from './pages/AgentsPage';
import RegisterPage from './pages/RegisterPage';

function App() {
  const [authState, setAuthState] = useState(AuthService.getInstance().getAuthState());
  const [darkMode, setDarkMode] = useState(() => {
    return localStorage.getItem('lss-dark-mode') === 'true';
  });

  useEffect(() => {
    applyMode(darkMode ? Mode.Dark : Mode.Light);
    localStorage.setItem('lss-dark-mode', String(darkMode));
  }, [darkMode]);

  useEffect(() => {
    const unsubscribe = AuthService.getInstance().subscribe(setAuthState);
    return unsubscribe;
  }, []);

  // Loading
  if (authState.loading) {
    return (
      <Container>
        <Box textAlign="center" padding="xxl">
          <Spinner size="large" />
          <Box variant="p" padding={{ top: 'm' }}>Loading...</Box>
        </Box>
      </Container>
    );
  }

  // Not authenticated — show login form
  if (!authState.isAuthenticated) {
    return (
      <LoginForm onLoginSuccess={() => {
        setAuthState(AuthService.getInstance().getAuthState());
      }} />
    );
  }

  // Authenticated — show the app
  return (
    <BrowserRouter>
      <Layout darkMode={darkMode} onToggleDarkMode={() => setDarkMode((d) => !d)}>
        <Routes>
          <Route path="/" element={<Navigate to="/chat" replace />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/register" element={<RegisterPage />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
