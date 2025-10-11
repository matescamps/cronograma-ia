const path = require('path')

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,
  
  // Forçar processamento de CSS
  sassOptions: {
    includePaths: [path.join(__dirname, 'styles')],
  },
  
  webpack: (config, { isServer }) => {
    // Forçar processamento de CSS mesmo no servidor
    if (isServer) {
      const originalEntry = config.entry;
      config.entry = async () => {
        const entries = { ...(await originalEntry()) };
        entries['global-styles'] = './app/globals.css';
        return entries;
      };
    }

    // Garantir que o CSS seja processado corretamente
    config.module.rules.push({
      test: /\.css$/,
      use: [
        'style-loader',
        {
          loader: 'css-loader',
          options: {
            importLoaders: 1,
            modules: {
              auto: true,
            },
          },
        },
        'postcss-loader',
      ],
    });

    return config;
  },

  // Garantir que o CSS seja incluído no build
  experimental: {
    optimizeCss: true,
    forceSwcTransforms: true,
  },
}