/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  output: 'standalone',
  // Configurações para o Framer Motion
  experimental: {
    optimizeCss: true,
  },
  // Configurações de ambiente
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
  },
  // Configurações de imagens
  images: {
    domains: ['localhost'],
    unoptimized: true,
  },
  // Configuração de tipagem
  typescript: {
    ignoreBuildErrors: false,
  },
  // Configuração de compilação
  compiler: {
    // Remover console.logs em produção
    removeConsole: process.env.NODE_ENV === 'production',
  },
  // Configurações de otimização
  poweredByHeader: false,
  compress: true,
}