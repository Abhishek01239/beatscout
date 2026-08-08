export function LogoIcon() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" fill="none" aria-hidden>
      <rect x="1" y="1" width="30" height="30" rx="8" fill="#6d5ef2" />
      <rect x="9" y="12" width="2.6" height="8" rx="1.3" fill="white" opacity="0.9" />
      <rect x="14.7" y="9" width="2.6" height="14" rx="1.3" fill="white" opacity="0.7" />
      <rect x="20.4" y="13" width="2.6" height="6" rx="1.3" fill="white" opacity="0.5" />
    </svg>
  );
}

export function WaveformBars({ className }: { className?: string }) {
  const bars = Array.from({ length: 9 });
  return (
    <span className={className} aria-hidden>
      {bars.map((_, i) => (
        <span
          key={i}
          className="mx-0.5 inline-block w-1 rounded-full bg-accent-soft/70"
          style={{ height: `${8 + ((i * 7) % 14)}px` }}
        />
      ))}
    </span>
  );
}