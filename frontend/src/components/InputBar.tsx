import { useRef, useEffect } from 'react';

interface InputBarProps {
  onSend: (text: string) => void;
  onStop: () => void;
  onClear: () => void;
  streaming: boolean;
}

export default function InputBar({ onSend, onStop, onClear, streaming }: InputBarProps) {
  const textRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    textRef.current?.focus();
  }, [streaming]);

  const autoGrow = () => {
    const el = textRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  };

  const handleSend = () => {
    const text = textRef.current?.value.trim();
    if (!text || streaming) return;
    onSend(text);
    if (textRef.current) {
      textRef.current.value = '';
      textRef.current.style.height = 'auto';
    }
  };

  const hasText = () => (textRef.current?.value.trim().length ?? 0) > 0;

  return (
    <footer className="input-bar">
      <div className="input-wrap">
        <button className="icon-btn clear-btn" onClick={onClear} title="Clear conversation">
          <svg viewBox="0 0 20 20" fill="none">
            <path
              d="M4 6h12M8 6V4h4v2M7 6v9a1 1 0 001 1h4a1 1 0 001-1V6H7z"
              stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
            />
          </svg>
        </button>

        <textarea
          ref={textRef}
          className="prompt-input"
          placeholder="Ask anything…"
          rows={1}
          autoComplete="off"
          spellCheck={false}
          onInput={autoGrow}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
        />

        {streaming ? (
          <button className="icon-btn stop-btn" onClick={onStop} title="Stop task">
            <svg viewBox="0 0 20 20" fill="currentColor">
              <rect x="5" y="5" width="10" height="10" rx="2" />
            </svg>
          </button>
        ) : (
          <button
            className="icon-btn send-btn"
            onClick={handleSend}
            title="Send"
            disabled={!hasText()}
          >
            <svg viewBox="0 0 20 20" fill="none">
              <path
                d="M10 3v14M3 10l7-7 7 7"
                stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"
              />
            </svg>
          </button>
        )}
      </div>
    </footer>
  );
}
