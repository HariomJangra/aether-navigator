import { useRef, useEffect } from 'react';
import type { ChatMessage } from '../api';
import EmptyState from './EmptyState';
import ToolSteps from './ToolSteps';

interface ChatAreaProps {
  messages: ChatMessage[];
  isEmpty: boolean;
}

export default function ChatArea({ messages, isEmpty }: ChatAreaProps) {
  const areaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (areaRef.current) {
      areaRef.current.scrollTop = areaRef.current.scrollHeight;
    }
  }, [messages]);

  if (isEmpty) {
    return (
      <main className="chat-area" ref={areaRef}>
        <EmptyState />
      </main>
    );
  }

  // Group messages: consecutive tool_call/tool_result are grouped together
  const groups: (ChatMessage | ChatMessage[])[] = [];
  let toolBuffer: ChatMessage[] = [];

  const flushTools = () => {
    if (toolBuffer.length > 0) {
      groups.push([...toolBuffer]);
      toolBuffer = [];
    }
  };

  for (const msg of messages) {
    if (msg.role === 'tool_call' || msg.role === 'tool_result') {
      toolBuffer.push(msg);
    } else {
      flushTools();
      groups.push(msg);
    }
  }
  flushTools();

  return (
    <main className="chat-area" ref={areaRef}>
      <div className="messages">
        {groups.map((group, i) => {
          if (Array.isArray(group)) {
            return <ToolSteps key={i} steps={group as (Extract<ChatMessage, { role: 'tool_call' }> | Extract<ChatMessage, { role: 'tool_result' }>)[]} />;
          }

          const msg = group;

          if (msg.role === 'user') {
            return (
              <div className="msg user" key={i}>
                <div className="msg-role">You</div>
                <div className="msg-bubble">{msg.text}</div>
              </div>
            );
          }

          if (msg.role === 'ai') {
            return (
              <div className="msg ai" key={i}>
                <div className="msg-role">{msg.error ? 'Error' : 'Agent'}</div>
                <div
                  className="msg-bubble"
                  style={msg.error ? { color: '#dc2626' } : msg.stopped ? { color: '#92400e' } : undefined}
                >
                  {msg.text || <TypingDots />}
                </div>
              </div>
            );
          }

          return null;
        })}
      </div>
    </main>
  );
}

function TypingDots() {
  return (
    <span className="typing-dots">
      <span /><span /><span />
    </span>
  );
}
