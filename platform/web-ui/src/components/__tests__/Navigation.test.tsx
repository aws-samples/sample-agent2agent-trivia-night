/**
 * Unit tests for Navigation and Layout components.
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */
import { describe, it, expect } from 'vitest';
import React from 'react';
import { render } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Navigation from '../Navigation';
import Layout from '../Layout';

describe('Navigation', () => {
  it('renders Chat section with Chat Assistant link', () => {
    const { container } = render(
      <MemoryRouter>
        <Navigation activeHref="/chat" />
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('Chat');
    expect(text).toContain('Chat Assistant');
  });

  it('renders Agent Registry section with Agents and Register Agent links', () => {
    const { container } = render(
      <MemoryRouter>
        <Navigation activeHref="/agents" />
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('Agent Registry');
    expect(text).toContain('Agents');
    expect(text).toContain('Register Agent');
  });

  it('renders LSS Workshop header', () => {
    const { container } = render(
      <MemoryRouter>
        <Navigation />
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('LSS Workshop');
  });
});

describe('Layout', () => {
  it('renders breadcrumbs with root item for /chat', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/chat']}>
        <Layout>
          <div>Chat content</div>
        </Layout>
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('LSS Workshop');
    expect(text).toContain('Chat Assistant');
  });

  it('renders breadcrumbs for /agents', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/agents']}>
        <Layout>
          <div>Agents content</div>
        </Layout>
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('LSS Workshop');
    expect(text).toContain('Agents');
  });

  it('renders breadcrumbs for /register', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/register']}>
        <Layout>
          <div>Register content</div>
        </Layout>
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('LSS Workshop');
    expect(text).toContain('Register Agent');
  });

  it('renders children content', () => {
    const { getByText } = render(
      <MemoryRouter initialEntries={['/chat']}>
        <Layout>
          <div>My test content</div>
        </Layout>
      </MemoryRouter>,
    );
    expect(getByText('My test content')).toBeTruthy();
  });

  it('renders flash notifications when provided', () => {
    const notifications = [
      { type: 'error' as const, content: 'Something went wrong', id: '1', dismissible: true },
    ];
    const { container } = render(
      <MemoryRouter initialEntries={['/chat']}>
        <Layout notifications={notifications}>
          <div>Content</div>
        </Layout>
      </MemoryRouter>,
    );
    const text = container.textContent ?? '';
    expect(text).toContain('Something went wrong');
  });
});
