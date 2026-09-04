"use client";

import React, { useState } from "react";
import "./globals.css";
import { Navbar } from "@/components/Navbar";
import { StreakModal } from "@/components/StreakModal";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [isStreaksOpen, setIsStreaksOpen] = useState(false);

  return (
    <html lang="en">
      <head>
        <title>NFL Daily Mini-Games Platform</title>
        <meta name="description" content="Daily NFL trivia mini-games: 3x3 Grid, Connections, and Top 10 Leaderboards." />
      </head>
      <body className="bg-background text-white min-h-screen flex flex-col antialiased selection:bg-nfl-blue selection:text-white">
        <Navbar onOpenStreaks={() => setIsStreaksOpen(true)} />
        <main className="flex-1 w-full max-w-5xl mx-auto px-4 py-8">
          {children}
        </main>
        <footer className="border-t border-border py-6 text-center text-xs text-gray-500">
          <p>© {new Date().getFullYear()} NFL Daily Mini-Games. Powered by nflverse datasets.</p>
        </footer>
        <StreakModal isOpen={isStreaksOpen} onClose={() => setIsStreaksOpen(false)} />
      </body>
    </html>
  );
}
