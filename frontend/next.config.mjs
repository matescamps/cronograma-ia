/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  compiler: {
    styledComponents: true,
  },
  sassOptions: {
    includePaths: ['./styles'],
  },
  experimental: {
    optimizeCss: true,
  },
}