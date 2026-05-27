import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
    // Proxy all /api/backend/* requests to the FastAPI backend
    // This avoids cross-origin issues when accessing via port-forwarding,
    // remote environments, or Codespaces where only port 3000 is exposed.
    async rewrites() {
        return [
            {
                source: '/api/backend/:path*',
                destination: 'http://localhost:8000/:path*',
            },
        ]
    },
}

export default nextConfig