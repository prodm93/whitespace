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
            <radialGradient id="bulb-glow-grad" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--text-primary)" stopOpacity="0.6" />
              <stop offset="60%" stopColor="var(--accent)" stopOpacity="0.15" />
              <stop offset="100%" stopColor="var(--accent)" stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* ── Knowledge graph (lower-left) ── */}
          <line className="hg-edge" x1="45" y1="295" x2="95" y2="262" />
          <line className="hg-edge" x1="45" y1="295" x2="62" y2="340" />
          <line className="hg-edge" x1="45" y1="295" x2="140" y2="330" />
          <line className="hg-edge" x1="95" y1="262" x2="142" y2="272" />
          <line className="hg-edge" x1="95" y1="262" x2="118" y2="252" />
          <line className="hg-edge" x1="142" y1="272" x2="185" y2="284" />
          <line className="hg-edge" x1="142" y1="272" x2="140" y2="330" />
          <line className="hg-edge" x1="142" y1="272" x2="118" y2="252" />
          <line className="hg-edge" x1="185" y1="284" x2="200" y2="338" />
          <line className="hg-edge" x1="62" y1="340" x2="140" y2="330" />
          <line className="hg-edge" x1="62" y1="340" x2="90" y2="378" />
          <line className="hg-edge" x1="140" y1="330" x2="200" y2="338" />
          <line className="hg-edge" x1="140" y1="330" x2="160" y2="375" />
          <line className="hg-edge" x1="140" y1="330" x2="90" y2="378" />
          <line className="hg-edge" x1="200" y1="338" x2="202" y2="310" />
          <line className="hg-edge" x1="90" y1="378" x2="55" y2="398" />
          <line className="hg-edge" x1="90" y1="378" x2="120" y2="385" />
          <line className="hg-edge" x1="62" y1="340" x2="120" y2="385" />
          <circle className="hg-node" cx="45" cy="295" r="9" />
          <circle className="hg-node" cx="95" cy="262" r="5" />
          <circle className="hg-node" cx="142" cy="272" r="5.5" />
          <circle className="hg-node" cx="185" cy="284" r="5" />
          <circle className="hg-node" cx="62" cy="340" r="5.5" />
          <circle className="hg-node" cx="140" cy="330" r="10" />
          <circle className="hg-node" cx="200" cy="338" r="5" />
          <circle className="hg-node" cx="90" cy="378" r="5" />
          <circle className="hg-node" cx="118" cy="252" r="3" />
          <circle className="hg-node" cx="202" cy="310" r="3.5" />
          <circle className="hg-node" cx="160" cy="375" r="3" />
          <circle className="hg-node" cx="55" cy="398" r="3" />
          <circle className="hg-detach" cx="120" cy="385" r="3.5" />

          {/* ── Outlined hero text ── */}
          <text
            x="600" y="150" textAnchor="middle"
            fill="none" stroke="var(--text-primary)" strokeWidth="0.8"
            style={{
              fontFamily: '"Cormorant Garamond", Georgia, serif',
              fontSize: "48px", fontWeight: 300, fontStyle: "italic",
              letterSpacing: "0.04em",
            }}
          >Find your</text>
          <text
            x="600" y="310" textAnchor="middle"
            fill="none" stroke="var(--text-primary)" strokeWidth="1.2"
            style={{
              fontFamily: '"Cormorant Garamond", Georgia, serif',
              fontSize: "160px", fontWeight: 600, letterSpacing: "0.02em",
            }}
          >whitespace</text>

          {/* ── Arc (shortened, graph → head) ── */}
          <path
            className="hero-arc"
            d="M 120,385 C 250,318 420,130 660,195 C 850,240 970,108 1044,102"
            fill="none" stroke="var(--stroke-cream)" strokeWidth="1"
          />
          <path
            className="hero-arc-alt"
            d="M 135,393 C 265,326 435,124 675,187 C 865,232 985,96 1058,90"
            fill="none" stroke="var(--stroke-lavender)" strokeWidth="0.6"
          />
          <circle className="hero-traveller" r="3.5" fill="var(--text-primary)" opacity="0" />

          {/* ── Head profile + lightbulb line drawing ── */}
          <g transform="translate(1665,20) scale(-0.63,0.63)" fill="none">
          <path
            className="hb-head"
            d="M 1040,238 C 1038,246 1040,253 1042,260 C 1052,272 1064,282 1067,292 C 1069,300 1058,302 1048,303 C 1055,309 1054,314 1044,315 C 1038,315 1035,319 1041,323 C 1049,329 1061,332 1062,344 C 1063,361 1035,372 990,373 C 958,374 935,380 926,398 C 920,411 926,427 946,438"
            stroke="var(--stroke-cream)" strokeWidth="1.2"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <path
            className="hb-detail"
            d="M 1037,318 C 1045,316 1052,318 1056,322"
          />
          <path
            className="hb-detail"
            d="M 1038,330 C 1047,334 1055,333 1060,329"
          />
          <path
            className="hb-brain"
            d="M 808,380 C 816,342 807,313 784,282 C 742,226 760,145 823,105 C 895,58 1005,75 1041,150 C 1054,176 1048,210 1040,238"
          />
          <path
            className="hb-brain"
            d="M 815,302 C 835,260 874,242 906,255 C 944,271 948,309 924,337 C 900,365 856,372 840,350 C 827,331 841,309 867,292"
          />
          <path
            className="hb-brain"
            d="M 812,219 C 838,205 870,215 896,242 C 922,270 981,274 1005,253 C 1023,237 1014,221 982,224 C 932,228 865,224 823,199"
          />
          <path
            className="hb-brain"
            d="M 827,171 C 817,143 840,118 876,119 C 909,121 920,151 905,177 C 893,198 861,193 860,169 C 859,147 882,132 902,146"
          />
          <path
            className="hb-brain"
            d="M 910,172 C 900,142 928,114 960,120 C 991,126 995,158 975,182 C 959,199 932,190 934,168 C 936,145 959,132 978,149"
          />
          <path
            className="hb-brain"
            d="M 981,179 C 980,156 999,138 1020,145 C 1041,153 1040,181 1022,193 C 1005,203 986,194 981,179"
          />
          <path
            className="hb-brain"
            d="M 1040,238 C 1030,235 1020,240 1005,253"
          />
          <path
            className="hb-bulb"
            d="M 1084,222 C 1084,198 1065,180 1059,151 C 1049,104 1080,74 1125,75 C 1171,76 1199,112 1187,157 C 1180,184 1159,199 1156,222"
            stroke="var(--text-primary)" strokeWidth="1.1"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <path
            className="hb-filament"
            d="M 1104,222 C 1105,190 1104,160 1098,142 C 1091,121 1070,130 1077,148 C 1084,164 1104,155 1110,138 C 1116,119 1098,115 1098,135 C 1098,156 1122,157 1128,137 C 1134,118 1116,119 1120,141 C 1125,162 1124,191 1124,222"
            stroke="var(--text-primary)" strokeWidth="0.8"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <path className="hb-base" d="M 1087,224 C 1102,216 1139,216 1155,224" />
          <path className="hb-base" d="M 1085,232 C 1101,225 1141,225 1157,232" />
          <path className="hb-base" d="M 1088,240 C 1105,234 1139,234 1154,240" />
          <path className="hb-base" d="M 1092,249 C 1109,244 1135,244 1150,249" />
          <path className="hb-base" d="M 1100,257 C 1112,266 1133,263 1144,254" />
          </g>

          {/* ── Star accents ── */}
          <g className="hero-star" transform="translate(290, 248)">
            <path d="M 0,-8 L 1.8,-1.8 L 8,0 L 1.8,1.8 L 0,8 L -1.8,1.8 L -8,0 L -1.8,-1.8 Z" fill="var(--text-primary)" />
          </g>
          <g className="hero-star" transform="translate(1150, 195)">
            <path d="M 0,-7 L 1.5,-1.5 L 7,0 L 1.5,1.5 L 0,7 L -1.5,1.5 L -7,0 L -1.5,-1.5 Z" fill="var(--text-primary)" />
          </g>
          <g className="hero-star" transform="translate(880, 78)">
            <path d="M 0,-9 L 2,-2 L 9,0 L 2,2 L 0,9 L -2,2 L -9,0 L -2,-2 Z" fill="var(--text-primary)" />
          </g>
        </svg>

        <p className="hero__tagline">Find the gaps. Own the ideas.</p>
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
        .hero__svg { width: 100%; max-width: 960px; height: auto; }
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
        .hg-edge { stroke: var(--stroke-cream); stroke-width: 0.7; opacity: 0.85; }
        .hg-node, .hg-detach { fill: none; stroke: var(--stroke-cream); stroke-width: 0.8; }
        .hb-brain { stroke: var(--stroke-cream); stroke-width: 0.9; stroke-linecap: round; fill: none; }
        .hb-detail { stroke: var(--stroke-cream); stroke-width: 0.9; stroke-linecap: round; fill: none; }
        .hb-ray { stroke: var(--text-primary); stroke-width: 0.9; stroke-linecap: round; }
        .hb-base { stroke: var(--text-primary); stroke-width: 1; stroke-linecap: round; fill: none; }
        @media (max-width: 600px) {
          .hero { padding: 80px var(--margin) 48px; }
        }
      `}</style>
    </section>
  );
}
