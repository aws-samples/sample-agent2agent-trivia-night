/**
 * Unit tests for ChatPanel component.
 * Requirements: 5.4, 5.5, 5.6, 5.7
 */
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, fireEvent } from '@testing-library/react';
import ChatPanel, { ChatMessage } from '../ChatPanel';

const mockSend = vi.fn();

const sampleMessages: ChatMessage[] = [
  { id: '1', role: 'user', content: 'Hello agent', timestamp: 1000 },
  { id: '2', role: 'agent', content: 'Hi there! How can I help?', timestamp: 2000 },
  { id: '3', role: 'user', content: 'Tell me about life sciences', timestamp: 3000 },
];

describe('ChatPanel', () => {
  it('renders empty state when no messages', () => {
    const { getByText } = render(
      <ChatPanel messages={[]} onSendMessage={mockSend} />,
    );
    expect(getByText('Send a message to start the conversation.')).toBeTruthy();
  });

  it('renders all messages as chat bubbles', () => {
    const { getAllByTestId } = render(
      <ChatPanel messages={sampleMessages} onSendMessage={mockSend} />,
    );
    const userBubbles = getAllByTestId('chat-bubble-user');
    const agentBubbles = getAllByTestId('chat-bubble-agent');
    expect(userBubbles.length).toBe(2);
    expect(agentBubbles.length).toBe(1);
  });

  it('displays message content correctly', () => {
    const { getByText } = render(
      <ChatPanel messages={sampleMessages} onSendMessage={mockSend} />,
    );
    expect(getByText('Hello agent')).toBeTruthy();
    expect(getByText('Hi there! How can I help?')).toBeTruthy();
    expect(getByText('Tell me about life sciences')).toBeTruthy();
  });

  it('shows loading indicator when loading is true', () => {
    const { getByTestId } = render(
      <ChatPanel messages={sampleMessages} loading onSendMessage={mockSend} />,
    );
    expect(getByTestId('chat-loading')).toBeTruthy();
  });

  it('does not show loading indicator when loading is false', () => {
    const { queryByTestId } = render(
      <ChatPanel messages={sampleMessages} loading={false} onSendMessage={mockSend} />,
    );
    expect(queryByTestId('chat-loading')).toBeNull();
  });

  it('displays inline error message when error is provided', () => {
    const { getByTestId } = render(
      <ChatPanel
        messages={sampleMessages}
        error="Agent is unreachable"
        onSendMessage={mockSend}
      />,
    );
    const errorEl = getByTestId('chat-error');
    expect(errorEl.textContent).toContain('Agent is unreachable');
  });

  it('does not display error when error is null', () => {
    const { queryByTestId } = render(
      <ChatPanel messages={sampleMessages} error={null} onSendMessage={mockSend} />,
    );
    expect(queryByTestId('chat-error')).toBeNull();
  });

  it('disables send button when disabled prop is true', () => {
    const { getByTestId } = render(
      <ChatPanel messages={[]} disabled onSendMessage={mockSend} />,
    );
    const sendBtn = getByTestId('chat-send-button');
    expect(sendBtn.querySelector('button')?.disabled ?? sendBtn.hasAttribute('disabled')).toBeTruthy;
  });

  it('renders the chat panel container', () => {
    const { getByTestId } = render(
      <ChatPanel messages={[]} onSendMessage={mockSend} />,
    );
    expect(getByTestId('chat-panel')).toBeTruthy();
  });
});
