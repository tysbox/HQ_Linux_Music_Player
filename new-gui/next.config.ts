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
          // 重要: チャンク名がビルド間で同一になる場合があり、その場合ブラウザーが
          // 古い JS/CSS をキャッシュから使い続けて GUI 変更が反映されない。
          // → immutable をやめ、毎回 ETag 再検証（304 は軽量）させる。
          { key: "Cache-Control", value: "no-cache, must-revalidate" },
        ],
      },
    ];
  },
};

export default nextConfig;