import React, { useState } from 'react';
import {
  AppLayout,
  BreadcrumbGroup,
  BreadcrumbGroupProps,
  Flashbar,
  FlashbarProps,
  Toggle,
  SpaceBetween,
} from '@cloudscape-design/components';
import { useLocation, useNavigate } from 'react-router-dom';
import Navigation from './Navigation';

interface LayoutProps {
  children: React.ReactNode;
  notifications?: FlashbarProps.MessageDefinition[];
  darkMode?: boolean;
  onToggleDarkMode?: () => void;
}

/** Map route paths to breadcrumb labels */
const ROUTE_LABELS: Record<string, string> = {
  '/chat': 'Chat Assistant',
  '/agents': 'Agents',
  '/register': 'Register Agent',
};

const Layout: React.FC<LayoutProps> = ({ children, notifications = [], darkMode = false, onToggleDarkMode }) => {
  const [navOpen, setNavOpen] = useState(true);
  const location = useLocation();
  const navigate = useNavigate();

  const currentPath = location.pathname;

  /* ---- Breadcrumbs reflecting current navigation path ---- */
  const breadcrumbItems: BreadcrumbGroupProps.Item[] = [
    { text: 'LSS Workshop', href: '/' },
  ];

  const label = ROUTE_LABELS[currentPath];
  if (label) {
    breadcrumbItems.push({ text: label, href: currentPath });
  }

  return (
    <AppLayout
      navigation={
        <SpaceBetween size="m">
          <Navigation activeHref={currentPath} />
          {onToggleDarkMode && (
            <div style={{ padding: '0 20px' }}>
              <Toggle checked={darkMode} onChange={onToggleDarkMode}>
                Dark mode
              </Toggle>
            </div>
          )}
        </SpaceBetween>
      }
      navigationOpen={navOpen}
      onNavigationChange={({ detail }) => setNavOpen(detail.open)}
      breadcrumbs={
        <BreadcrumbGroup
          items={breadcrumbItems}
          onFollow={(e) => {
            e.preventDefault();
            if (e.detail.href) navigate(e.detail.href);
          }}
        />
      }
      notifications={
        notifications.length > 0 ? <Flashbar items={notifications} /> : undefined
      }
      content={children}
      toolsHide
      contentType="default"
      stickyNotifications
    />
  );
};

export default Layout;
