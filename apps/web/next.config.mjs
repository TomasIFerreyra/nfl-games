/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@nfl-games/contracts"],
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "a.espncdn.com",
      },
      {
        protocol: "https",
        hostname: "static.www.nfl.com",
      },
      {
        protocol: "https",
        hostname: "static.nfl.com",
      },
      {
        protocol: "https",
        hostname: "sleepercdn.com",
      },
      {
        protocol: "https",
        hostname: "images.sportslogos.net",
      },
      {
        protocol: "https",
        hostname: "raw.githubusercontent.com",
      },
      {
        protocol: "https",
        hostname: "upload.wikimedia.org",
      },
    ],
  },
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: process.env.API_URL
          ? `${process.env.API_URL}/api/v1/:path*`
          : "http://127.0.0.1:8000/api/v1/:path*",
      },
    ];
  },
};

export default nextConfig;
