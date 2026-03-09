import { useState } from 'react';
import type { ChatMessage } from '../api';

type ToolMsg = Extract<ChatMessage, { role: 'tool_call' }> | Extract<ChatMessage, { role: 'tool_result' }>;

interface ToolStepProps {
  steps: ToolMsg[];
}

function formatArgs(args: Record<string, unknown>): string {
  return Object.entries(args)
    .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
    .join('\n');
}

export default function ToolSteps({ steps }: ToolStepProps) {
  const [expanded, setExpanded] = useState(true);

  if (steps.length === 0) return null;

  const pairs: { call: Extract<ChatMessage, { role: 'tool_call' }>; result?: Extract<ChatMessage, { role: 'tool_result' }> }[] = [];
  for (let i = 0; i < steps.length; i++) {
    const s = steps[i];
    if (s.role === 'tool_call') {
      const next = steps[i + 1];
      if (next && next.role === 'tool_result') {
        pairs.push({ call: s, result: next });
        i++;
      } else {
        pairs.push({ call: s });
      }
    }
  }

  const toolIcons: Record<string, string> = {
    snapshot: '📸',
    navigate: '🧭',
    interact: '👆',
  };

  const lastPair = pairs[pairs.length - 1];
  const isRunning = lastPair && !lastPair.result;

  return (
    <div className="tool-steps-container">
      <button
        className={`tool-steps-toggle ${expanded ? 'expanded' : ''}`}
        onClick={() => setExpanded(!expanded)}
      >
        <div className="tool-steps-summary">
          {isRunning && <span className="tool-spinner" />}
          {!isRunning && (
            <svg className="tool-check-icon" viewBox="0 0 16 16" fill="none">
              <path d="M3 8.5l3.5 3.5 6.5-7" stroke="#16a34a" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
            </svg>
          )}
          <span className="tool-steps-label">
            {isRunning
              ? `Running ${lastPair.call.name}…`
              : `Used ${pairs.length} tool${pairs.length > 1 ? 's' : ''}`
            }
          </span>
        </div>
        <svg className="tool-chevron" viewBox="0 0 16 16" fill="none">
          <path d="M5 6l3 3 3-3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>

      {expanded && (
        <div className="tool-steps-detail">
          {pairs.map((pair, i) => (
            <div className="tool-step" key={i}>
              <div className="tool-step-line" />
              <div className="tool-step-dot">
                <span>{toolIcons[pair.call.name] || '⚙️'}</span>
              </div>
              <div className="tool-step-content">
                <div className="tool-step-header">
                  <span className="tool-step-name">{pair.call.name}</span>
                  {pair.result
                    ? <span className="tool-step-badge done">done</span>
                    : <span className="tool-step-badge running">running</span>
                  }
                </div>
                <pre className="tool-step-args">{formatArgs(pair.call.args)}</pre>
                {pair.result && (
                  <div className="tool-step-result">{pair.result.preview}</div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
