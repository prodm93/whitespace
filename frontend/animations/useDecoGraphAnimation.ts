"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

gsap.registerPlugin(MotionPathPlugin);

export function useDecoGraphAnimation() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
      svg.querySelectorAll(".dg-node").forEach((n) => {
        gsap.set(n, { opacity: 0.7 });
      });
      svg.querySelectorAll(".dg-edge, .dg-orbit").forEach((e) => {
        gsap.set(e, { strokeDashoffset: 0 });
      });
      return;
    }

    const tweens: gsap.core.Tween[] = [];

    const orbits = svg.querySelectorAll<SVGPathElement>(".dg-orbit");
    orbits.forEach((orbit, i) => {
      const len = orbit.getTotalLength();
      gsap.set(orbit, { strokeDasharray: len, strokeDashoffset: len });
      tweens.push(
        gsap.to(orbit, {
          strokeDashoffset: 0,
          duration: 2.6,
          ease: "power2.inOut",
          delay: i * 0.3,
        }),
      );
    });

    const edges = svg.querySelectorAll<SVGPathElement>(".dg-edge");
    edges.forEach((edge, i) => {
      const len = edge.getTotalLength();
      gsap.set(edge, { strokeDasharray: len, strokeDashoffset: len });
      tweens.push(
        gsap.to(edge, {
          strokeDashoffset: 0,
          duration: 1.2,
          ease: "power2.inOut",
          delay: 0.6 + i * 0.12,
        }),
      );
    });

    const nodes = svg.querySelectorAll(".dg-node");
    nodes.forEach((node, i) => {
      gsap.set(node, { opacity: 0, scale: 0.3, transformOrigin: "center" });
      tweens.push(
        gsap.to(node, {
          opacity: 0.85,
          scale: 1,
          duration: 0.5,
          ease: "power2.out",
          delay: 1.0 + i * 0.1,
        }),
      );
      tweens.push(
        gsap.to(node, {
          opacity: 0.4,
          scale: 0.8,
          duration: 2.5 + i * 0.4,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 2.0 + i * 0.3,
        }),
      );
    });

    const travellers = svg.querySelectorAll(".dg-traveller");
    travellers.forEach((dot, i) => {
      const edgeList = Array.from(edges);
      const path = edgeList[i % edgeList.length];
      if (!path) return;
      gsap.set(dot, { opacity: 0 });
      tweens.push(
        gsap.to(dot, { opacity: 0.8, duration: 0.3, delay: 2.2 }),
      );
      tweens.push(
        gsap.to(dot, {
          motionPath: { path, align: path, alignOrigin: [0.5, 0.5] },
          duration: 4 + i * 0.8,
          repeat: -1,
          ease: "none",
          delay: 2.2 + i * 0.6,
        }),
      );
    });

    const stars = svg.querySelectorAll(".dg-star");
    stars.forEach((star, i) => {
      gsap.set(star, { opacity: 0, scale: 0.5, transformOrigin: "center" });
      tweens.push(
        gsap.to(star, {
          opacity: 0.6,
          scale: 1,
          duration: 0.6,
          ease: "power2.out",
          delay: 1.8 + i * 0.4,
        }),
      );
      tweens.push(
        gsap.to(star, {
          opacity: 0.25,
          scale: 0.8,
          duration: 3,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 2.8 + i * 0.5,
        }),
      );
    });

    return () => {
      tweens.forEach((t) => t.kill());
    };
  }, []);

  return svgRef;
}
