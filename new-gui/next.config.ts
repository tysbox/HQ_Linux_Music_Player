import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  // HTML ドキュメントをブラウザー/プロキシにキャッシュさせない
  // （GUI 更新後に古いページ＋古いチャンクが残る問題を防止）
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "Cache-Control", value: "no-store, must-revalidate" },
        ],
      },
      {
        source: "/_next/static/:path*",
        headers: [
          // 静的チャンクは内容ハッシュ付き URL なので長期キャッシュ可
          { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
        ],
      },
    ];
  },
};

export default nextConfig;