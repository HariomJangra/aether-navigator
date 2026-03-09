interface HeaderProps {
  contextCount: number;
}

export default function Header({ contextCount }: HeaderProps) {
  return (
    <header className="header">
      <div className="logo-wrap">
        <svg className="logo-icon" viewBox="0 0 40 40" fill="none">
          <path
            d="M20 5C11.716 5 5 11.716 5 20s6.716 15 15 15 15-6.716 15-15S28.284 5 20 5z"
            fill="none" stroke="#999" strokeWidth="2"
          />
          <path
            d="M20 10C13.373 10 8 15.373 8 22s5.373 12 12 12"
            stroke="#888" strokeWidth="2.5" strokeLinecap="round"
          />
          <path
            d="M20 10C26.627 10 32 15.373 32 22"
            stroke="#bbb" strokeWidth="2.5" strokeLinecap="round"
          />
        </svg>
        <span className="logo-text">Aether Navigator</span>
      </div>
      <div className="context-badge" title="Messages in memory">
        {contextCount} in context
      </div>
    </header>
  );
}
