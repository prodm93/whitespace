"use client";

import { useHeroAnimation } from "@/animations/useHeroAnimation";

export default function Hero() {
  const svgRef = useHeroAnimation();

  return (
    <section className="hero">
      <div className="hero__inner">
        <svg
          ref={svgRef}
          className="hero__svg"
          viewBox="0 60 1200 360"
          preserveAspectRatio="xMidYMid meet"
          aria-hidden="true"
        >
          <defs>
            <radialGradient id="star-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--text-primary)" stopOpacity="0.8" />
              <stop offset="100%" stopColor="var(--text-primary)" stopOpacity="0" />
            </radialGradient>
            <radialGradient id="apex-glow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--text-primary)" stopOpacity="0.5" />
              <stop offset="50%" stopColor="var(--accent)" stopOpacity="0.1" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Outlined "Find your" */}
          <text
            x="600"
            y="150"
            textAnchor="middle"
            className="hero__text-find"
            fill="none"
            stroke="var(--text-primary)"
            strokeWidth="0.8"
            style={{
              fontFamily: '"Cormorant Garamond", Georgia, serif',
              fontSize: "48px",
              fontWeight: 300,
              fontStyle: "italic",
              letterSpacing: "0.04em",
            }}
          >
            Find your
          </text>

          {/* Outlined "whitespace" */}
          <text
            x="600"
            y="310"
            textAnchor="middle"
            className="hero__text-main"
            fill="none"
            stroke="var(--text-primary)"
            strokeWidth="1.2"
            style={{
              fontFamily: '"Cormorant Garamond", Georgia, serif',
              fontSize: "160px",
              fontWeight: 600,
              letterSpacing: "0.02em",
            }}
          >
            whitespace
          </text>

          {/* Primary arc — sweeping trajectory through the letterforms */}
          <path
            className="arc-path"
            d="M 20,400 C 160,330 400,100 680,180 C 880,230 1020,80 1190,90"
            fill="none"
            stroke="var(--stroke-cream)"
            strokeWidth="1"
          />

          {/* Secondary arc — slightly offset, thinner, creates a trajectory ribbon */}
          <path
            className="arc-path-secondary"
            d="M 35,410 C 175,335 415,95 695,170 C 895,220 1035,70 1195,75"
            fill="none"
            stroke="var(--stroke-lavender)"
            strokeWidth="0.6"
          />

          {/* Apex glow — where the arcs converge upper-right */}
          <circle
            className="arc-apex-glow"
            cx="1100"
            cy="65"
            r="24"
            fill="url(#apex-glow)"
            opacity="0"
          />

          {/* Travelling dot on primary arc */}
          <circle
            className="arc-dot"
            r="4"
            fill="var(--text-primary)"
            opacity="0"
          />

          {/* Four-point star accents */}
          <g className="star-accent" transform="translate(140, 100)">
            <path
              d="M 0,-12 L 2.5,-2.5 L 12,0 L 2.5,2.5 L 0,12 L -2.5,2.5 L -12,0 L -2.5,-2.5 Z"
              fill="var(--text-primary)"
              opacity="0.7"
            />
          </g>

          <g className="star-accent" transform="translate(1050, 380)">
            <path
              d="M 0,-16 L 3,-3 L 16,0 L 3,3 L 0,16 L -3,3 L -16,0 L -3,-3 Z"
              fill="var(--text-primary)"
              opacity="0.7"
            />
          </g>

          <g className="star-accent" transform="translate(920, 80)">
            <path
              d="M 0,-9 L 2,-2 L 9,0 L 2,2 L 0,9 L -2,2 L -9,0 L -2,-2 Z"
              fill="var(--text-primary)"
              opacity="0.5"
            />
          </g>

          {/* Apex starburst — small four-point star at arc convergence */}
          <g className="arc-apex-star" transform="translate(1100, 62)">
            <path
              d="M 0,-8 L 1.8,-1.8 L 8,0 L 1.8,1.8 L 0,8 L -1.8,1.8 L -8,0 L -1.8,-1.8 Z"
              fill="var(--text-primary)"
              opacity="0"
            />
          </g>
        </svg>

        <p className="hero__tagline">
          Find the gaps. Own the ideas.
        </p>
      </div>

      <style jsx>{`
        .hero {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 80px var(--margin) 48px;
          overflow: hidden;
        }
        .hero__inner {
          position: relative;
          width: 100%;
          max-width: 1200px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        .hero__svg {
          width: 100%;
          max-width: 900px;
          height: auto;
        }
        .hero__tagline {
          margin-top: 24px;
          font-family: "Inter", sans-serif;
          font-size: var(--text-body);
          font-weight: 300;
          color: var(--text-secondary);
          letter-spacing: 0.06em;
          text-transform: uppercase;
          text-align: center;
        }

        @media (max-width: 600px) {
          .hero {
            padding: 80px var(--margin) 48px;
          }
        }
      `}</style>
    </section>
  );
}
