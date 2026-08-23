import type { NextConfig } from "next";

/**
 * The browser never talks to the FastAPI backend directly.
 *
 * Every call goes through a Next.js route handler, which attaches the access token from
 * an httpOnly cookie. That keeps tokens out of JavaScript entirely — an XSS bug cannot
 * read a cookie it is not allowed to see — and removes cross-origin cookie handling.
 *
 * The consequence is that `API_BASE_URL` is a *server* variable. It is deliberately not
 * `NEXT_PUBLIC_`: nothing about the backend's location reaches the bundle.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,

  // Fail the build on type errors rather than shipping them. It is the default; stated
  // explicitly so nobody "temporarily" disables it.
  //
  // Next 16 no longer runs ESLint as part of `next build`, so linting is a separate CI
  // step (`pnpm --filter web lint`) rather than a config flag here.
  typescript: { ignoreBuildErrors: false },

  // Do not advertise the framework version to every visitor.
  poweredByHeader: false,

  // Next 16 blocks cross-origin requests to dev-only resources. Playwright drives the
  // app on 127.0.0.1 while the dev server assumes localhost, so HMR requests are
  // rejected and fill the console with 403s. Development only; no effect on a build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],

  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
