/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  devIndicators: false,
  reactCompiler: true,
  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
  async redirects() {
    return [
      { source: "/dashboard/logistics", destination: "/dashboard/gigca", permanent: false },
      {
        source: "/dashboard",
        destination: "/dashboard/gigca",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    const backend = process.env.GIGCA_API_URL || "http://127.0.0.1:8000";
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
};

export default nextConfig;
