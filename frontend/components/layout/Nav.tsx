"use client";

import Link from "next/link";

export default function Nav() {
  return (
    <nav className="nav">
      <div className="nav__inner">
        <Link href="/" className="nav__wordmark">
          WhiteSpace
        </Link>
      </div>

      <style jsx>{`
        .nav {
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          z-index: 100;
          padding: 0 var(--margin);
          backdrop-filter: blur(12px);
          background: rgba(8, 9, 26, 0.6);
          border-bottom: 1px solid var(--stroke-cream);
        }
        .nav__inner {
          max-width: 1280px;
          margin: 0 auto;
          height: 64px;
          display: flex;
          align-items: center;
        }
        .nav__wordmark {
          font-family: "Cormorant Garamond", "Georgia", serif;
          font-size: 22px;
          font-weight: 500;
          letter-spacing: 0.02em;
          color: var(--text-primary);
          transition: opacity 0.2s var(--ease-out);
        }
        .nav__wordmark:hover {
          opacity: 0.8;
        }
      `}</style>
    </nav>
  );
}
