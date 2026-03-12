import React from 'react';
import { SideNavigation, SideNavigationProps } from '@cloudscape-design/components';
import { useNavigate } from 'react-router-dom';

interface NavigationProps {
  activeHref?: string;
}

const Navigation: React.FC<NavigationProps> = ({ activeHref = '/chat' }) => {
  const navigate = useNavigate();

  const navigationItems: SideNavigationProps.Item[] = [
    {
      type: 'section',
      text: 'Chat',
      items: [
        { type: 'link', text: 'Chat Assistant', href: '/chat' },
      ],
    },
    {
      type: 'section',
      text: 'Agent Registry',
      items: [
        { type: 'link', text: 'Agents', href: '/agents' },
        { type: 'link', text: 'Register Agent', href: '/register' },
      ],
    },
  ];

  const handleFollow: SideNavigationProps['onFollow'] = (event) => {
    event.preventDefault();
    if (event.detail.href) {
      navigate(event.detail.href);
    }
  };

  return (
    <SideNavigation
      activeHref={activeHref}
      header={{ href: '/', text: 'LSS Workshop' }}
      items={navigationItems}
      onFollow={handleFollow}
    />
  );
};

export default Navigation;
