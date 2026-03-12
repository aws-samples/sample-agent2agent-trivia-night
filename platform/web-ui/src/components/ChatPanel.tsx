import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Input,
  SpaceBetween,
  Spinner,
} from '@cloudscape-design/components';
import Markdown from 'react-markdown';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface ChatMessage {
  id: string;
  role: 'user' | 'agent';
  content: string;
  timestamp: number;
}

export interface ChatPanelProps {
  /** Ordered list of messages to display */
  messages: ChatMessage[];
  /** Whether an API call is in flight */
  loading?: boolean;
  /** Current error message (displayed inline) */
  error?: string | null;
  /** Called when the user submits a new message */
  onSendMessage: (message: string) => void;
  /** Whether the send button should be disabled (e.g. no agent selected) */
  disabled?: boolean;
  /** Placeholder text for the input */
  placeholder?: string;
}

/* ------------------------------------------------------------------ */
/*  Styles (inline to avoid external CSS dependency)                   */
/* ------------------------------------------------------------------ */

const containerStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'column',
  height: '100%',
  minHeight: 400,
};

const messagesContainerStyle: React.CSSProperties = {
  flex: 1,
  overflowY: 'auto',
  padding: '16px',
  display: 'flex',
  flexDirection: 'column',
  gap: '12px',
};

const bubbleBase: React.CSSProperties = {
  maxWidth: '75%',
  padding: '10px 14px',
  borderRadius: '12px',
  wordBreak: 'break-word',
  whiteSpace: 'pre-wrap',
  lineHeight: 1.5,
};

const userBubbleStyle: React.CSSProperties = {
  ...bubbleBase,
  alignSelf: 'flex-end',
  backgroundColor: '#0972d3',
  color: '#ffffff',
};

const agentBubbleStyle: React.CSSProperties = {
  ...bubbleBase,
  alignSelf: 'flex-start',
  backgroundColor: '#f2f3f3',
  color: '#000716',
  whiteSpace: 'normal',
};

const inputBarStyle: React.CSSProperties = {
  display: 'flex',
  gap: '8px',
  padding: '12px 16px',
  borderTop: '1px solid #e9ebed',
};

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

const ChatPanel: React.FC<ChatPanelProps> = ({
  messages,
  loading = false,
  error = null,
  onSendMessage,
  disabled = false,
  placeholder = 'Type a message…',
}) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  /* ---- Auto-scroll to bottom on new messages or loading change ---- */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  /* ---- Submit handler ---- */
  const handleSend = () => {
    const trimmed = inputValue.trim();
    if (!trimmed || disabled || loading) return;
    onSendMessage(trimmed);
    setInputValue('');
  };

  const handleKeyDown = (e: CustomEvent<{ key: string }>) => {
    if ((e.detail as any).key === 'Enter' || (e as any).detail?.keyCode === 13) {
      handleSend();
    }
  };

  return (
    <div style={containerStyle} data-testid="chat-panel">
      {/* ---- Messages area ---- */}
      <div style={messagesContainerStyle} data-testid="chat-messages">
        {messages.length === 0 && !loading && (
          <Box textAlign="center" color="text-status-inactive" padding="xxl">
            Send a message to start the conversation.
          </Box>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            style={msg.role === 'user' ? userBubbleStyle : agentBubbleStyle}
            data-testid={`chat-bubble-${msg.role}`}
          >
            {msg.role === 'agent' ? (
              <Markdown>{msg.content}</Markdown>
            ) : (
              msg.content
            )}
          </div>
        ))}

        {/* ---- Loading indicator ---- */}
        {loading && (
          <div style={{ alignSelf: 'flex-start', padding: '8px 0' }} data-testid="chat-loading">
            <SpaceBetween direction="horizontal" size="xs">
              <Spinner size="normal" />
              <Box color="text-status-inactive">Agent is thinking…</Box>
            </SpaceBetween>
          </div>
        )}

        {/* ---- Inline error ---- */}
        {error && (
          <div style={{ alignSelf: 'stretch' }} data-testid="chat-error">
            <Alert type="error">{error}</Alert>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* ---- Input bar ---- */}
      <div style={inputBarStyle}>
        <div style={{ flex: 1 }}>
          <Input
            value={inputValue}
            onChange={({ detail }) => setInputValue(detail.value)}
            onKeyDown={handleKeyDown as any}
            placeholder={placeholder}
            disabled={disabled || loading}
            data-testid="chat-input"
          />
        </div>
        <Button
          variant="primary"
          onClick={handleSend}
          disabled={disabled || loading || !inputValue.trim()}
          data-testid="chat-send-button"
        >
          Send
        </Button>
      </div>
    </div>
  );
};

export default ChatPanel;
