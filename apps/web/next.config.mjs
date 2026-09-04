/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@nfl-games/contracts"],
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
