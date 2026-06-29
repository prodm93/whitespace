"use client";

import { type ReactNode } from "react";
import Nav from "./Nav";

export default function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <Nav />
      <main className="app-shell__content">{children}</main>

      <style jsx>{`
        .app-shell {
          min-height: 100vh;
          display: flex;
          flex-direction: column;
          background: linear-gradient(
            168deg,
            var(--bg-top) 0%,
            var(--bg-mid) 45%,
            var(--bg-bottom) 100%
          );
        }
        .app-shell__content {
          flex: 1;
        }
      `}</style>
    </div>
  );
}
