"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";

export function useHeadLightbulbAnimation() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
      svg.querySelectorAll(".head-stroke, .bulb-stroke").forEach((el) => {
        gsap.set(el, { strokeDashoffset: 0, opacity: 1 });
      });
      svg.querySelectorAll(".bulb-ray").forEach((el) => {
        gsap.set(el, { opacity: 0.5 });
      });
      const glow = svg.querySelector(".bulb-glow");
      if (glow) gsap.set(glow, { opacity: 0.12 });
      return;
    }

    const tweens: gsap.core.Tween[] = [];

    const headPath = svg.querySelector(".head-stroke") as SVGPathElement | null;
    if (headPath) {
      const len = headPath.getTotalLength();
      gsap.set(headPath, { strokeDasharray: len, strokeDashoffset: len });
      tweens.push(
        gsap.to(headPath, {
          strokeDashoffset: 0,
          duration: 2.2,
          ease: "power2.inOut",
        }),
      );
    }

    const bulbPath = svg.querySelector(".bulb-stroke") as SVGPathElement | null;
    if (bulbPath) {
      const len = bulbPath.getTotalLength();
      gsap.set(bulbPath, { strokeDasharray: len, strokeDashoffset: len });
      tweens.push(
        gsap.to(bulbPath, {
          strokeDashoffset: 0,
          duration: 1.0,
          ease: "power2.out",
          delay: 1.8,
        }),
      );
    }

    const rays = svg.querySelectorAll(".bulb-ray");
    rays.forEach((ray, i) => {
      gsap.set(ray, { opacity: 0, scale: 0.4, transformOrigin: "center" });
      tweens.push(
        gsap.to(ray, {
          opacity: 0.6,
          scale: 1,
          duration: 0.5,
          ease: "power2.out",
          delay: 2.6 + i * 0.08,
        }),
      );
      tweens.push(
        gsap.to(ray, {
          opacity: 0.2,
          scale: 0.7,
          duration: 2.0 + i * 0.3,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 3.4 + i * 0.15,
        }),
      );
    });

    const glow = svg.querySelector(".bulb-glow");
    if (glow) {
      gsap.set(glow, { opacity: 0 });
      tweens.push(
        gsap.to(glow, {
          opacity: 0.18,
          duration: 0.8,
          ease: "power2.out",
          delay: 2.5,
        }),
      );
      tweens.push(
        gsap.to(glow, {
          opacity: 0.06,
          duration: 3,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 3.5,
        }),
      );
    }

    return () => {
      tweens.forEach((t) => t.kill());
    };
  }, []);

  return svgRef;
}
