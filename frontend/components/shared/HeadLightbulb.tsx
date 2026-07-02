"use client";

import { useHeadLightbulbAnimation } from "@/animations/useHeadLightbulbAnimation";

interface HeadLightbulbProps {
  className?: string;
  width?: number;
  height?: number;
}

export default function HeadLightbulb({
  className,
  width = 160,
  height = 220,
}: HeadLightbulbProps) {
  const svgRef = useHeadLightbulbAnimation();

  return (
    <svg
      ref={svgRef}
      className={className}
      width={width}
      height={height}
      viewBox="0 0 160 220"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="bulb-glow-grad" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="var(--text-primary)" stopOpacity="0.6" />
          <stop offset="60%" stopColor="var(--accent)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* Glow behind the bulb */}
      <circle
        className="bulb-glow"
        cx="94"
        cy="38"
        r="28"
        fill="url(#bulb-glow-grad)"
        opacity="0"
      />

      {/* Head profile — single continuous stroke, abstract, right-facing */}
      <path
        className="head-stroke"
        d={[
          "M 56,190",
          "C 46,168 38,130 42,95",
          "C 46,60 62,42 78,44",
          "C 86,45 92,50 96,58",
          "C 99,64 101,70 102,76",
          "C 104,82 103,88 100,91",
          "C 97,94 95,95 95,100",
          "C 95,104 97,108 95,113",
          "C 91,122 84,138 78,154",
          "C 72,168 66,180 62,188",
        ].join(" ")}
        stroke="var(--stroke-cream)"
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Lightbulb shape — above the crown */}
      <path
        className="bulb-stroke"
        d={[
          "M 86,52",
          "C 82,40 84,24 94,20",
          "C 104,16 112,26 110,38",
          "C 108,46 104,50 100,52",
          "L 92,52",
          "C 88,52 86,50 86,48",
        ].join(" ")}
        stroke="var(--text-primary)"
        strokeWidth="1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Connector — brain squiggle into filament */}
      <path
        className="head-stroke"
        d="M 78,44 C 83,43 89,44 94,46"
        stroke="var(--stroke-cream)"
        strokeWidth="1"
        strokeLinecap="round"
      />

      {/* Filament — tiny zigzag inside bulb */}
      <path
        className="bulb-stroke"
        d="M 94,46 L 96,40 L 92,36 L 98,32"
        stroke="var(--text-primary)"
        strokeWidth="0.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />

      {/* Rays — short emanating lines */}
      <line className="bulb-ray" x1="97" y1="14" x2="97" y2="6" stroke="var(--text-primary)" strokeWidth="0.8" strokeLinecap="round" />
      <line className="bulb-ray" x1="80" y1="22" x2="73" y2="17" stroke="var(--text-primary)" strokeWidth="0.8" strokeLinecap="round" />
      <line className="bulb-ray" x1="114" y1="22" x2="121" y2="17" stroke="var(--text-primary)" strokeWidth="0.8" strokeLinecap="round" />
      <line className="bulb-ray" x1="76" y1="38" x2="68" y2="38" stroke="var(--text-primary)" strokeWidth="0.8" strokeLinecap="round" />
      <line className="bulb-ray" x1="118" y1="38" x2="126" y2="38" stroke="var(--text-primary)" strokeWidth="0.8" strokeLinecap="round" />
    </svg>
  );
}
