/**
 * The Velora mark, as inline SVG.
 *
 * Two linked loops with a lit node at their intersection: an agent and an
 * authority, joined at the point where a decision happens. Reproduced as
 * vector rather than a raster asset so it stays sharp, inherits colour, and
 * can animate — the node pulses while the engine is evaluating.
 */

export function LogoMark({ size = 28, live = false, className = '' }) {
  return (
    <svg width={size} height={size * 0.62}
      viewBox="0 0 100 62" fill="none"
      className={className} aria-hidden="true"
    >
      {/* Small loop — the agent */}
      <ellipse cx="26" cy="31" rx="24" ry="20" stroke="currentColor"
        strokeWidth="3" opacity="0.9"
      />
      {/* Large loop — the authority */}
      <ellipse cx="62" cy="31" rx="35" ry="29" stroke="currentColor"
        strokeWidth="3" opacity="0.9"
      />
      {/* The decision point */}
      <circle cx="43" cy="31" r="7" fill="currentColor">
        {live && (
          <animate
            attributeName="r" values="7;9;7" dur="2.4s"
            repeatCount="indefinite"
          />
        )}
      </circle>
    </svg>
  )
}

export function Logo({ size = 26, live = false, subtitle, className = '' }) {
  return (
    <div className={`flex items-center gap-3 ${className}`}>
      <LogoMark size={size * 1.5} live={live} className="text-brand-500" />
      <div className="leading-none">
        <div
          className="font-semibold tracking-tight text-fg" style={{ fontSize: size * 0.72 }}
        >
          velora
        </div>
        {subtitle && (
          <div className="mt-1 eyebrow text-fg-faint uppercase">
            {subtitle}
          </div>
        )}
      </div>
    </div>
  )
}

export default Logo
