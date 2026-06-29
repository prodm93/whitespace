"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

gsap.registerPlugin(MotionPathPlugin);

export function useGraphAnimation() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
      svg.querySelectorAll(".graph-dot").forEach((d) => {
        gsap.set(d, { opacity: 0.6 });
      });
      return;
    }

    const paths = svg.querySelectorAll<SVGPathElement>(".graph-edge");
    const travellers = svg.querySelectorAll(".graph-traveller");
    const dots = svg.querySelectorAll(".graph-dot");

    const tweens: gsap.core.Tween[] = [];

    paths.forEach((path) => {
      const len = path.getTotalLength();
      gsap.set(path, { strokeDasharray: len, strokeDashoffset: len });
      tweens.push(
        gsap.to(path, {
          strokeDashoffset: 0,
          duration: 1.6,
          ease: "power2.inOut",
        }),
      );
    });

    dots.forEach((dot, i) => {
      gsap.set(dot, { opacity: 0, scale: 0.5, transformOrigin: "center" });
      tweens.push(
        gsap.to(dot, {
          opacity: 0.8,
          scale: 1,
          duration: 0.6,
          ease: "power2.out",
          delay: 0.3 + i * 0.15,
        }),
      );
      tweens.push(
        gsap.to(dot, {
          opacity: 0.4,
          scale: 0.85,
          duration: 2 + i * 0.3,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 1.2 + i * 0.2,
        }),
      );
    });

    travellers.forEach((traveller, i) => {
      const path = paths[i % paths.length];
      if (!path) return;
      gsap.set(traveller, { opacity: 0 });
      tweens.push(
        gsap.to(traveller, { opacity: 1, duration: 0.3, delay: 1 }),
      );
      tweens.push(
        gsap.to(traveller, {
          motionPath: {
            path,
            align: path,
            alignOrigin: [0.5, 0.5],
          },
          duration: 3 + i * 0.5,
          repeat: -1,
          ease: "none",
          delay: 1,
        }),
      );
    });

    return () => {
      tweens.forEach((t) => t.kill());
    };
  }, []);

  return svgRef;
}
