import { useId } from "react";

/**
 * The AI Software Factory mark: a shaded isometric cube (the thing being built) on a teal tile, with an AI spark
 * above its corner. Matches public/favicon.svg.
 */
export function Logo({ size = 24 }: { size?: number }) {
  const gid = `asf-g${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden data-testid="asf-mark">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#14B8A6" />
          <stop offset="1" stopColor="#0E7490" />
        </linearGradient>
      </defs>
      <rect width="100" height="100" rx="26" fill={`url(#${gid})`} />
      <g stroke={`url(#${gid})`} strokeWidth="3" strokeLinejoin="round">
        <path d="M50 29 71.65 41.5 50 54 28.35 41.5Z" fill="#fff" />
        <path d="M28.35 41.5 50 54v25L28.35 66.5Z" fill="#fff" fillOpacity="0.55" />
        <path d="M50 54 71.65 41.5v25L50 79Z" fill="#fff" fillOpacity="0.8" />
      </g>
      <path
        d="M78 12c1.1 6.6 2.4 7.9 9 9-6.6 1.1-7.9 2.4-9 9-1.1-6.6-2.4-7.9-9-9 6.6-1.1 7.9-2.4 9-9Z"
        fill="#fff"
      />
    </svg>
  );
}
