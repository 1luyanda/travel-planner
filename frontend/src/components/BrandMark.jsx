export default function BrandMark({ className }) {
  return (
    <svg className={className} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="13" fill="none" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="16" cy="16" r="2" fill="currentColor" />
      <path d="M16 5.5 18.2 16 16 26.5 13.8 16Z" fill="var(--tp-accent)" />
      <path d="M5.5 16 16 13.8 26.5 16 16 18.2Z" fill="var(--tp-text)" opacity="0.85" />
    </svg>
  )
}
