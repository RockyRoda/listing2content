/**
 * Static export: `next build` writes a fully static site to `out/`, which the
 * FastAPI backend serves. Trailing slashes make each route its own
 * `route/index.html`, which StaticFiles(html=True) serves directly.
 */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

export default nextConfig;
