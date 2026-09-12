import Link from "next/link";
import { ArrowLeft, Compass } from "lucide-react";

export default function NotFound() {
  return (
    <div className="min-h-[50vh] flex flex-col items-center justify-center text-center px-4 py-12">
      <div className="w-16 h-16 bg-zinc-900 border border-zinc-700 rounded-full flex items-center justify-center mb-4 text-zinc-400 shadow-lg">
        <Compass size={32} />
      </div>
      <h2 className="text-2xl font-black tracking-tight text-white mb-2">
        Page Not Found
      </h2>
      <p className="text-gray-400 text-sm max-w-md mb-6 leading-relaxed">
        The requested mini-game or leaderboard page does not exist.
      </p>
      <Link
        href="/"
        className="flex items-center gap-2 bg-nfl-blue hover:bg-nfl-blue/90 text-white font-bold py-2.5 px-6 rounded-lg transition-colors shadow-lg active:scale-95"
      >
        <ArrowLeft size={16} /> Return to Games Hub
      </Link>
    </div>
  );
}
