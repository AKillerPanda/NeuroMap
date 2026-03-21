import { useId } from "react";

interface NeuroMapLogoProps {
  className?: string;
  ariaLabel?: string;
}

export function NeuroMapLogo({ className = "size-8", ariaLabel = "NeuroMap logo" }: NeuroMapLogoProps) {
  const idPrefix = useId();
  const gradient1Id = `${idPrefix}-gradient1`;
  const gradient2Id = `${idPrefix}-gradient2`;
  const gradient3Id = `${idPrefix}-gradient3`;
  
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label={ariaLabel}
    >
      {/* Connection lines (synapses/edges) */}
      <path
        d="M30 25 L50 50 M70 25 L50 50 M30 75 L50 50 M70 75 L50 50 M30 25 L70 75 M70 25 L30 75"
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2"
        strokeLinecap="round"
        opacity="0.4"
      />
      
      {/* Central node (largest) */}
      <circle
        cx="50"
        cy="50"
        r="12"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2.5"
      />
      
      {/* Top nodes */}
      <circle
        cx="30"
        cy="25"
        r="8"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2"
      />
      <circle
        cx="70"
        cy="25"
        r="8"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2"
      />
      
      {/* Bottom nodes */}
      <circle
        cx="30"
        cy="75"
        r="8"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2"
      />
      <circle
        cx="70"
        cy="75"
        r="8"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="2"
      />
      
      {/* Side nodes (smaller) */}
      <circle
        cx="15"
        cy="50"
        r="6"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="1.5"
      />
      <circle
        cx="85"
        cy="50"
        r="6"
        fill={`url(#${gradient2Id})`}
        stroke={`url(#${gradient1Id})`}
        strokeWidth="1.5"
      />
      
      {/* Additional small nodes for brain-like complexity */}
      <circle cx="50" cy="20" r="5" fill={`url(#${gradient3Id})`} opacity="0.8" />
      <circle cx="50" cy="80" r="5" fill={`url(#${gradient3Id})`} opacity="0.8" />
      <circle cx="20" cy="35" r="4" fill={`url(#${gradient3Id})`} opacity="0.7" />
      <circle cx="80" cy="35" r="4" fill={`url(#${gradient3Id})`} opacity="0.7" />
      <circle cx="20" cy="65" r="4" fill={`url(#${gradient3Id})`} opacity="0.7" />
      <circle cx="80" cy="65" r="4" fill={`url(#${gradient3Id})`} opacity="0.7" />
      
      {/* Gradients */}
      <defs>
        <linearGradient id={gradient1Id} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#7c3aed" />
          <stop offset="100%" stopColor="#2563eb" />
        </linearGradient>
        <linearGradient id={gradient2Id} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#a78bfa" />
          <stop offset="100%" stopColor="#60a5fa" />
        </linearGradient>
        <linearGradient id={gradient3Id} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#3b82f6" />
        </linearGradient>
      </defs>
    </svg>
  );
}
