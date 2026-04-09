export type SSEEvent =
  | { type: 'tool_call'; name: string; args: Record<string, unknown> }
  | { type: 'tool_result'; name: string; preview: string }
  | { type: 'ai_message'; content: string }
  | { type: 'stopped'; content: string }
  | { type: 'error'; content: string }
  | { type: 'done' };

export type ChatMessage =
  | { role: 'user'; text: string }
  | { role: 'ai'; text: string; error?: boolean; stopped?: boolean }
  | { role: 'tool_call'; name: string; args: Record<string, unknown> }
  | { role: 'tool_result'; name: string; preview: string };

export async function streamChat(
  message: string,
  onEvent: (evt: SSEEvent) => void,
  signal?: AbortSignal,
) {
  const resp = await fetch('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    signal,
  });

  if (!resp.ok) throw new Error(`Server error ${resp.status}`);

  const reader = resp.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        onEvent(JSON.parse(raw));
      } catch { /* skip malformed */ }
    }
  }
}

export async function stopTask() {
  await fetch('/stop', { method: 'POST' });
}

export async function clearMemory() {
  await fetch('/clear', { method: 'POST' });
}

export async function fetchStatus(): Promise<number> {
  const r = await fetch('/status');
  const d = await r.json();
  return d.messages ?? 0;
}

export async function fetchContext(): Promise<{ role: string; content: string }[]> {
  const r = await fetch('/context');
  const d = await r.json();
  return d.messages ?? [];
}
