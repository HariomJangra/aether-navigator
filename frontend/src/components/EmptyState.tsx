export default function EmptyState() {
  return (
    <div className="empty-state">
      <svg className="empty-icon" viewBox="0 0 64 64" fill="none">
        <circle cx="32" cy="32" r="28" stroke="#ddd" strokeWidth="2" />
        <path
          d="M32 16C23.163 16 16 23.163 16 32s7.163 16 16 16 16-7.163 16-16-7.163-16-16-16z"
          fill="none" stroke="#ccc" strokeWidth="2"
        />
        <path d="M32 20C25.373 20 20 25.373 20 32" stroke="#bbb" strokeWidth="3" strokeLinecap="round" />
        <path d="M32 20C38.627 20 44 25.373 44 32" stroke="#ddd" strokeWidth="3" strokeLinecap="round" />
      </svg>
      <p className="empty-title">Ask me anything</p>
      <p className="empty-sub">I can browse the web, interact with pages, and automate tasks.</p>
    </div>
  );
}
