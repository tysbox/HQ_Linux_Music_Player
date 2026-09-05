import { test, expect } from "@playwright/test";

/**
 * Phase 3a-5 Task 4: hq_api ベースライン E2E テスト.
 *
 * 目的:
 * - unified-shell (port 3002) が正常に表示される
 * - hq_api:8002 からデータが取得できる
 * - 既存サービス（DSP:8000, DMP:8001）に無影響
 *
 * 注: shell は .env で DSP/DMP バックエンドを参照しているため、
 *     hq_api への切替は shell の NEXT_PUBLIC_* 環境変数変更が別途必要。
 *     ここでは shell 経由のデータ取得を間接的に確認する。
 */

const HQ_API = process.env.HQ_API_URL || "http://localhost:8002";
const DSP = process.env.DSP_URL || "http://localhost:8000";
const DMP = process.env.DMP_URL || "http://localhost:8001";

test.describe("hq_api (port 8002) 基本動作", () => {
  test("/health が ok を返す", async ({ request }) => {
    const res = await request.get(`${HQ_API}/health`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.status).toBe("ok");
    expect(body.mpd).toBe("connected");
  });

  test("/ がサービス情報を返す", async ({ request }) => {
    const res = await request.get(`${HQ_API}/`);
    expect(res.status()).toBe(200);
    const body = await res.json();
    expect(body.service).toContain("HQ Unified API");
    expect(body.status).toBe("running");
    expect(body.port).toBe(8002);
  });

  test("/api/devices が DSP:8000 と同一", async ({ request }) => {
    const [dsp, hq] = await Promise.all([
      request.get(`${DSP}/api/devices`),
      request.get(`${HQ_API}/api/devices`),
    ]);
    expect(dsp.status()).toBe(200);
    expect(hq.status()).toBe(200);
    const [dspBody, hqBody] = await Promise.all([dsp.json(), hq.json()]);
    expect(hqBody).toEqual(dspBody);
  });

  test("/api/library/artists が DMP:8001 と同一", async ({ request }) => {
    const [dmp, hq] = await Promise.all([
      request.get(`${DMP}/api/library/artists`),
      request.get(`${HQ_API}/api/library/artists`),
    ]);
    expect(dmp.status()).toBe(200);
    expect(hq.status()).toBe(200);
    const [dmpBody, hqBody] = await Promise.all([dmp.json(), hq.json()]);
    expect(hqBody).toEqual(dmpBody);
  });

  test("/api/now_playing が DSP:8000 と同一", async ({ request }) => {
    const [dsp, hq] = await Promise.all([
      request.get(`${DSP}/api/now_playing`),
      request.get(`${HQ_API}/api/now_playing`),
    ]);
    expect(dsp.status()).toBe(200);
    expect(hq.status()).toBe(200);
    const [dspBody, hqBody] = await Promise.all([dsp.json(), hq.json()]);
    expect(hqBody).toEqual(dspBody);
  });

  test("OpenAPI 仕様が 43 ルート以上を公開", async ({ request }) => {
    const res = await request.get(`${HQ_API}/openapi.json`);
    expect(res.status()).toBe(200);
    const spec = await res.json();
    const pathCount = Object.keys(spec.paths || {}).length;
    expect(pathCount).toBeGreaterThanOrEqual(43);
  });
});

test.describe("unified-shell (port 3002)", () => {
  test("トップページの HTML が返る", async ({ request }) => {
    const res = await request.get("http://localhost:3002/");
    expect(res.status()).toBe(200);
    const html = await res.text();
    expect(html).toMatch(/<html/i);
  });
});
