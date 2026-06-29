"use client";

import { useDecoGraphAnimation } from "@/animations/useDecoGraphAnimation";

interface GraphDecorationProps {
  className?: string;
  width?: number;
  height?: number;
}

export default function GraphDecoration({
  className,
  width = 400,
  height = 320,
}: GraphDecorationProps) {
  const svgRef = useDecoGraphAnimation();

  return (
    <svg
      ref={svgRef}
      className={className}
      width={width}
      height={height}
      viewBox="0 0 400 320"
      fill="none"
      aria-hidden="true"
    >
      {/* Orbit curves — large elegant sweeps like the Perpetuum reference */}
      <ellipse
        className="dg-orbit"
        cx="210"
        cy="160"
        rx="170"
        ry="100"
        transform="rotate(-12 210 160)"
        stroke="var(--stroke-cream)"
        strokeWidth="0.8"
      />
      <ellipse
        className="dg-orbit"
        cx="200"
        cy="155"
        rx="130"
        ry="80"
        transform="rotate(25 200 155)"
        stroke="var(--stroke-lavender)"
        strokeWidth="0.8"
        strokeDasharray="6 4"
      />

      {/* Edges — curved connections between node positions */}
      <path className="dg-edge" d="M 55,155 C 80,120 100,90 130,85" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 55,155 C 75,175 110,195 145,200" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 130,85 C 160,95 180,120 205,140" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 145,200 C 170,185 185,165 205,140" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 205,140 C 230,110 245,80 265,65" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 205,140 C 230,170 255,205 280,218" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 265,65 C 290,80 315,100 340,118" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 280,218 C 310,230 335,245 355,255" stroke="var(--stroke-cream)" strokeWidth="0.8" />
      <path className="dg-edge" d="M 340,118 C 350,150 355,200 355,255" stroke="var(--stroke-lavender)" strokeWidth="0.6" />

      {/* Nodes — small dots at graph vertices */}
      <circle className="dg-node" cx="55" cy="155" r="4" fill="var(--text-primary)" />
      <circle className="dg-node" cx="130" cy="85" r="3.5" fill="var(--text-primary)" />
      <circle className="dg-node" cx="145" cy="200" r="3" fill="var(--text-primary)" />
      <circle className="dg-node" cx="205" cy="140" r="5" fill="var(--text-primary)" />
      <circle className="dg-node" cx="265" cy="65" r="3.5" fill="var(--text-primary)" />
      <circle className="dg-node" cx="280" cy="218" r="3" fill="var(--text-primary)" />
      <circle className="dg-node" cx="340" cy="118" r="3.5" fill="var(--text-primary)" />
      <circle className="dg-node" cx="355" cy="255" r="3" fill="var(--text-primary)" />

      {/* Travelling dots — light moving along edges */}
      <circle className="dg-traveller" r="2" fill="var(--accent)" opacity="0" />
      <circle className="dg-traveller" r="2" fill="var(--accent)" opacity="0" />
      <circle className="dg-traveller" r="1.5" fill="var(--accent)" opacity="0" />

      {/* Four-point star accents */}
      <g className="dg-star" transform="translate(350, 42)">
        <path
          d="M 0,-10 L 2,-2 L 10,0 L 2,2 L 0,10 L -2,2 L -10,0 L -2,-2 Z"
          fill="var(--text-primary)"
          opacity="0.6"
        />
      </g>
      <g className="dg-star" transform="translate(28, 260)">
        <path
          d="M 0,-7 L 1.5,-1.5 L 7,0 L 1.5,1.5 L 0,7 L -1.5,1.5 L -7,0 L -1.5,-1.5 Z"
          fill="var(--text-primary)"
          opacity="0.5"
        />
      </g>
    </svg>
  );
}
