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
            <filter id="filament-glow" x="-80%" y="-80%" width="260%" height="260%">
              <feGaussianBlur stdDeviation="5" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
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
            d="M 120,385 C 250,326 420,148 660,228 C 850,284 970,160 1047,158"
            fill="none" stroke="var(--stroke-cream)" strokeWidth="1"
          />
          <path
            className="hero-arc-alt"
            d="M 135,393 C 265,334 435,142 675,220 C 865,276 985,148 1062,146"
            fill="none" stroke="var(--stroke-lavender)" strokeWidth="0.6"
          />
          <circle className="hero-traveller" r="3.5" fill="var(--text-primary)" opacity="0" />

          {/* ── Head profile + lightbulb line drawing ── */}
          <g transform="translate(1665,20) scale(-0.63,0.63)" fill="none">
          <path
            className="hb-head"
            d="M 1040,278 C 1038,286 1040,293 1042,300 C 1052,312 1064,322 1067,332 C 1069,340 1058,342 1048,343 C 1055,349 1054,354 1044,355 C 1038,355 1035,359 1041,363 C 1049,369 1061,372 1062,384 C 1063,401 1035,412 990,413 C 958,414 935,420 926,438 C 920,451 926,467 946,478"
            stroke="var(--stroke-cream)" strokeWidth="1.2"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <path
            className="hb-detail"
            d="M 1037,358 C 1045,356 1052,358 1056,362"
          />
          <path
            className="hb-detail"
            d="M 1038,370 C 1047,374 1055,373 1060,369"
          />
          <path
            className="hb-brain"
            d="M 808,420 C 816,382 807,353 784,322 C 742,266 760,185 823,145 C 895,98 1005,115 1041,190 C 1054,216 1048,250 1040,278"
          />
          <path
            className="hb-brain"
            d="M 815,342 C 835,300 874,282 906,295 C 944,311 948,349 924,377 C 900,405 856,412 840,390 C 827,371 841,349 867,332"
          />
          <path
            className="hb-brain"
            d="M 812,259 C 838,245 870,255 896,282 C 922,310 981,314 1005,293 C 1023,277 1014,261 982,264 C 932,268 865,264 823,239 C 810,230 812,218 827,211"
          />
          <path
            className="hb-brain"
            d="M 827,211 C 817,183 840,158 876,159 C 909,161 920,191 905,217 C 893,238 861,233 860,209 C 859,187 882,172 902,186"
          />
          <path
            className="hb-brain"
            d="M 910,212 C 900,182 928,154 960,160 C 991,166 995,198 975,222 C 959,239 932,230 934,208 C 936,185 959,172 978,189"
          />
          <path
            className="hb-brain"
            d="M 981,219 C 980,196 999,178 1020,185 C 1041,193 1040,221 1022,233 C 1005,243 986,234 981,219"
          />
          <g transform="translate(1120,148) scale(0.7) translate(-1120,-148)">
          <path
            className="hb-bulb"
            d="M 1084,222 C 1084,198 1065,180 1059,151 C 1049,104 1080,74 1125,75 C 1171,76 1199,112 1187,157 C 1180,184 1159,199 1156,222"
            stroke="var(--text-primary)" strokeWidth="1.1"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <circle
            className="hb-glow"
            cx="1120" cy="148" r="72"
            fill="url(#bulb-glow-grad)" opacity="0"
          />
          <path
            className="hb-filament-glow"
            d="M 1104,222 C 1105,190 1104,160 1098,142 C 1091,121 1070,130 1077,148 C 1084,164 1104,155 1110,138 C 1116,119 1098,115 1098,135 C 1098,156 1122,157 1128,137 C 1134,118 1116,119 1120,141 C 1125,162 1124,191 1124,222"
            stroke="var(--text-primary)" strokeWidth="4"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
            filter="url(#filament-glow)" opacity="0"
          />
          <path
            className="hb-filament"
            d="M 1104,222 C 1105,190 1104,160 1098,142 C 1091,121 1070,130 1077,148 C 1084,164 1104,155 1110,138 C 1116,119 1098,115 1098,135 C 1098,156 1122,157 1128,137 C 1134,118 1116,119 1120,141 C 1125,162 1124,191 1124,222"
            stroke="var(--text-primary)" strokeWidth="0.8"
            strokeLinecap="round" strokeLinejoin="round" fill="none"
          />
          <line className="hb-ray" x1="1120" y1="46" x2="1120" y2="14" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1078" y1="58" x2="1058" y2="34" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1162" y1="58" x2="1182" y2="34" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1050" y1="90" x2="1024" y2="80" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1190" y1="90" x2="1216" y2="80" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1042" y1="130" x2="1012" y2="130" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1198" y1="130" x2="1228" y2="130" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1050" y1="170" x2="1024" y2="180" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <line className="hb-ray" x1="1190" y1="170" x2="1216" y2="180" stroke="var(--text-primary)" strokeWidth="1" strokeLinecap="round" />
          <path className="hb-base" d="M 1087,224 C 1102,216 1139,216 1155,224" />
          <path className="hb-base" d="M 1085,232 C 1101,225 1141,225 1157,232" />
          <path className="hb-base" d="M 1088,240 C 1105,234 1139,234 1154,240" />
          <path className="hb-base" d="M 1092,249 C 1109,244 1135,244 1150,249" />
          <path className="hb-base" d="M 1100,257 C 1112,266 1133,263 1144,254" />
          </g>
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
