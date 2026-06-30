"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

gsap.registerPlugin(MotionPathPlugin);

function drawStroke(
  el: SVGGeometryElement, tl: gsap.core.Timeline,
  time: number, dur: number, ease = "power2.inOut",
) {
  const len = el.getTotalLength();
  gsap.set(el, { strokeDasharray: len, strokeDashoffset: len });
  tl.to(el, { strokeDashoffset: 0, duration: dur, ease }, time);
}

export function useHeroAnimation() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      svg.querySelectorAll(".hg-node, .hg-detach").forEach(n =>
        gsap.set(n, { opacity: 0.35 }),
      );
      svg.querySelectorAll(".hb-head, .hb-detail, .hb-bulb, .hb-filament, .hb-brain").forEach(p =>
        gsap.set(p, { opacity: 1 }),
      );
      svg.querySelectorAll(".hb-ray").forEach(r => gsap.set(r, { opacity: 0.4 }));
      svg.querySelectorAll(".hb-base").forEach(b => gsap.set(b, { opacity: 0.4 }));
      const g = svg.querySelector(".hb-glow");
      if (g) gsap.set(g, { opacity: 0.1 });
      svg.querySelectorAll(".hero-star").forEach(s => gsap.set(s, { opacity: 0.4 }));
      return;
    }

    const tl = gsap.timeline();
    const ambient: gsap.core.Tween[] = [];

    // ── Phase 1: Graph draws (0 – 2s) ──
    svg.querySelectorAll(".hg-edge").forEach((edge, i) => {
      drawStroke(edge as SVGGeometryElement, tl, i * 0.06, 0.6);
    });

    const nodes = svg.querySelectorAll(".hg-node");
    nodes.forEach((node, i) => {
      gsap.set(node, { opacity: 0, scale: 0.3, transformOrigin: "center" });
      tl.to(node, {
        opacity: 0.65, scale: 1, duration: 0.35, ease: "power2.out",
      }, 0.5 + i * 0.05);
    });

    const detach = svg.querySelector(".hg-detach");
    if (detach) {
      gsap.set(detach, { opacity: 0, scale: 0.3, transformOrigin: "center" });
      tl.to(detach, {
        opacity: 0.6, scale: 1, duration: 0.35, ease: "power2.out",
      }, 1.3);
    }

    // ── Phase 2: Detach fades, traveller spawns (2.2s) ──
    const traveller = svg.querySelector(".hero-traveller");
    const arcPath = svg.querySelector(".hero-arc") as SVGPathElement | null;

    if (detach && traveller && arcPath) {
      tl.to(detach, { opacity: 0.15, scale: 0.5, duration: 0.4 }, 2.2);
      gsap.set(traveller, { opacity: 0, attr: { cx: 120, cy: 385 } });
      tl.to(traveller, { opacity: 1, duration: 0.3 }, 2.3);

      // ── Phase 3: Arc + traverse (2.5 – 5.0s) ──
      const arcLen = arcPath.getTotalLength();
      gsap.set(arcPath, { strokeDasharray: arcLen, strokeDashoffset: arcLen });

      tl.to(traveller, {
        motionPath: { path: arcPath, align: arcPath, alignOrigin: [0.5, 0.5] },
        duration: 2.5, ease: "none",
      }, 2.5);

      tl.to(arcPath, {
        strokeDashoffset: 0, duration: 2.5, ease: "none",
      }, 2.65);
    }

    const altArc = svg.querySelector(".hero-arc-alt") as SVGPathElement | null;
    if (altArc) drawStroke(altArc, tl, 2.7, 2.5, "none");

    // ── Phase 4: Head + brain draws (3.2s) ──
    const headPath = svg.querySelector(".hb-head") as SVGGeometryElement | null;
    if (headPath) drawStroke(headPath, tl, 3.2, 1.6);

    svg.querySelectorAll(".hb-detail").forEach((detail, i) => {
      drawStroke(detail as SVGGeometryElement, tl, 3.5 + i * 0.08, 0.5);
    });

    svg.querySelectorAll(".hb-brain").forEach((brain, i) => {
      drawStroke(brain as SVGGeometryElement, tl, 3.8 + i * 0.15, 0.8);
    });

    // ── Phase 5: Bulb ignites (4.7s) ──
    if (traveller) {
      tl.to(traveller, { opacity: 0, duration: 0.3 }, 4.7);
    }

    const bulbPath = svg.querySelector(".hb-bulb") as SVGGeometryElement | null;
    const filament = svg.querySelector(".hb-filament") as SVGGeometryElement | null;
    if (bulbPath) drawStroke(bulbPath, tl, 4.7, 0.5);
    if (filament) drawStroke(filament, tl, 4.9, 0.3);

    svg.querySelectorAll(".hb-base").forEach((base, i) => {
      gsap.set(base, { opacity: 0 });
      tl.to(base, { opacity: 0.4, duration: 0.2, ease: "power2.out" }, 4.9 + i * 0.06);
    });

    const bulbGlow = svg.querySelector(".hb-glow");
    if (bulbGlow) {
      gsap.set(bulbGlow, { opacity: 0 });
      tl.to(bulbGlow, { opacity: 0.22, duration: 0.4, ease: "power2.out" }, 5.0);
    }

    const rays = svg.querySelectorAll(".hb-ray");
    rays.forEach((ray, i) => {
      gsap.set(ray, { opacity: 0 });
      tl.to(ray, { opacity: 0.7, duration: 0.3, ease: "power2.out" }, 5.2 + i * 0.06);
    });

    // Stars fade in during sequence
    const stars = svg.querySelectorAll(".hero-star");
    stars.forEach((star, i) => {
      gsap.set(star, { opacity: 0, scale: 0.5, transformOrigin: "center" });
      tl.to(star, {
        opacity: 0.5, scale: 1, duration: 0.6, ease: "power2.out",
      }, 1.5 + i * 0.5);
    });

    // ── Ambient loops ──
    nodes.forEach((node, i) => {
      ambient.push(gsap.to(node, {
        opacity: 0.3, duration: 2.5 + i * 0.3, repeat: -1, yoyo: true,
        ease: "sine.inOut", delay: 3 + i * 0.2,
      }));
    });

    stars.forEach((star, i) => {
      ambient.push(gsap.to(star, {
        opacity: 0.2, scale: 0.85, duration: 3 + i * 0.5, repeat: -1, yoyo: true,
        ease: "sine.inOut", delay: 3 + i * 0.4,
      }));
    });

    if (bulbGlow) {
      ambient.push(gsap.to(bulbGlow, {
        opacity: 0.06, duration: 3, repeat: -1, yoyo: true,
        ease: "sine.inOut", delay: 6,
      }));
    }

    rays.forEach((ray, i) => {
      ambient.push(gsap.to(ray, {
        opacity: 0.2, duration: 2 + i * 0.3, repeat: -1, yoyo: true,
        ease: "sine.inOut", delay: 6 + i * 0.1,
      }));
    });

    return () => {
      tl.kill();
      ambient.forEach(t => t.kill());
    };
  }, []);

  return svgRef;
}
