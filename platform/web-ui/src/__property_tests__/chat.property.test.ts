/**
 * Property 15: Conversation History Chronological Order
 *
 * For any sequence of chat messages in a session, the displayed messages
 * should appear in the order they were sent, with each message's position
 * index strictly increasing.
 *
 * Feature: lss-workshop-platform, Property 15: Conversation History Chronological Order
 * **Validates: Requirements 5.6**
 */
import { describe, it, expect, vi } from 'vitest';
import fc from 'fast-check';
import React from 'react';
import { render } from '@testing-library/react';
import ChatPanel, { ChatMessage } from '../components/ChatPanel';

/**
 * Arbitrary: generates a non-empty array of ChatMessage objects with
 * strictly increasing timestamps to represent a chronological conversation.
 */
const chatMessageArb: fc.Arbitrary<ChatMessage> = fc.record({
  id: fc.uuid(),
  role: fc.constantFrom<'user' | 'agent'>('user', 'agent'),
  content: fc.string({ minLength: 1, maxLength: 200 }),
  timestamp: fc.integer({ min: 0, max: Number.MAX_SAFE_INTEGER }),
});

const chronologicalMessagesArb: fc.Arbitrary<ChatMessage[]> = fc
  .array(chatMessageArb, { minLength: 1, maxLength: 20 })
  .map((msgs) =>
    msgs
      .sort((a, b) => a.timestamp - b.timestamp)
      .map((msg, idx) => ({ ...msg, timestamp: idx })),
  );

describe('Property 15: Conversation History Chronological Order', () => {
  it('renders messages in the same chronological order they are provided', () => {
    fc.assert(
      fc.property(chronologicalMessagesArb, (messages) => {
        const onSendMessage = vi.fn();
        const { getAllByTestId } = render(
          React.createElement(ChatPanel, {
            messages,
            onSendMessage,
          }),
        );

        const bubbles = getAllByTestId(/^chat-bubble-(user|agent)$/);

        // The number of rendered bubbles must match the number of messages
        expect(bubbles.length).toBe(messages.length);

        // Each bubble's text content must match the corresponding message in order
        for (let i = 0; i < messages.length; i++) {
          expect(bubbles[i].textContent).toBe(messages[i].content);
        }
      }),
      { numRuns: 100 },
    );
  });
});
