"use client";

import { useEffect, useRef } from "react";
import gsap from "gsap";
import { MotionPathPlugin } from "gsap/MotionPathPlugin";

gsap.registerPlugin(MotionPathPlugin);

export function useHeroAnimation() {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;

    const prefersReducedMotion = window.matchMedia(
      "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
      const dot = svg.querySelector(".arc-dot");
      if (dot) gsap.set(dot, { opacity: 1 });
      svg.querySelectorAll(".star-accent").forEach((star) => {
        gsap.set(star, { opacity: 0.6 });
      });
      const apexStar = svg.querySelector(".arc-apex-star");
      if (apexStar) gsap.set(apexStar, { opacity: 0.6 });
      const apexGlow = svg.querySelector(".arc-apex-glow");
      if (apexGlow) gsap.set(apexGlow, { opacity: 0.15 });
      return;
    }

    const tl = gsap.timeline({ defaults: { ease: "none" } });
    const standalone: gsap.core.Tween[] = [];

    // Draw primary arc
    const arcPath = svg.querySelector(".arc-path") as SVGPathElement | null;
    const dot = svg.querySelector(".arc-dot");

    if (arcPath && dot) {
      const length = arcPath.getTotalLength();
      gsap.set(arcPath, { strokeDasharray: length, strokeDashoffset: length });
      gsap.set(dot, { opacity: 0 });

      tl.to(arcPath, {
        strokeDashoffset: 0,
        duration: 2.4,
        ease: "power2.inOut",
      });

      tl.to(dot, { opacity: 1, duration: 0.3 }, 0.4);

      tl.to(
        dot,
        {
          motionPath: {
            path: arcPath,
            align: arcPath,
            alignOrigin: [0.5, 0.5],
          },
          duration: 8,
          repeat: -1,
          ease: "none",
        },
        0.4,
      );
    }

    // Draw secondary arc
    const secondaryPath = svg.querySelector(
      ".arc-path-secondary",
    ) as SVGPathElement | null;
    if (secondaryPath) {
      const len = secondaryPath.getTotalLength();
      gsap.set(secondaryPath, { strokeDasharray: len, strokeDashoffset: len });
      tl.to(
        secondaryPath,
        {
          strokeDashoffset: 0,
          duration: 2.6,
          ease: "power2.inOut",
        },
        0.2,
      );
    }

    // Apex glow + starburst appear after arcs draw
    const apexGlow = svg.querySelector(".arc-apex-glow");
    if (apexGlow) {
      gsap.set(apexGlow, { opacity: 0 });
      tl.to(apexGlow, { opacity: 0.2, duration: 0.8, ease: "power2.out" }, 2.0);
      standalone.push(
        gsap.to(apexGlow, {
          opacity: 0.06,
          duration: 3,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 3.0,
        }),
      );
    }

    const apexStar = svg.querySelector(".arc-apex-star");
    if (apexStar) {
      gsap.set(apexStar, { opacity: 0, scale: 0.3, transformOrigin: "center" });
      tl.to(
        apexStar,
        { opacity: 0.7, scale: 1, duration: 0.6, ease: "power2.out" },
        2.2,
      );
      standalone.push(
        gsap.to(apexStar, {
          opacity: 0.3,
          scale: 0.8,
          duration: 2.5,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 3.0,
        }),
      );
    }

    // Four-point star accents
    const stars = svg.querySelectorAll(".star-accent");
    stars.forEach((star, i) => {
      gsap.set(star, { opacity: 0, scale: 0.6, transformOrigin: "center" });

      tl.to(
        star,
        {
          opacity: 0.7,
          scale: 1,
          duration: 0.8,
          ease: "power2.out",
        },
        0.6 + i * 0.3,
      );

      standalone.push(
        gsap.to(star, {
          opacity: 0.35,
          scale: 0.85,
          duration: 2.5 + i * 0.4,
          repeat: -1,
          yoyo: true,
          ease: "sine.inOut",
          delay: 1.5 + i * 0.5,
        }),
      );
    });

    return () => {
      tl.kill();
      standalone.forEach((t) => t.kill());
      gsap.killTweensOf(dot);
    };
  }, []);

  return svgRef;
}
