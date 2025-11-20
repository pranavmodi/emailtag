/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // basePath NOT needed - app already has /settings2 in folder structure
  // Instead, nginx proxies both /settings2 and /_next/ to this server
};

module.exports = nextConfig;
