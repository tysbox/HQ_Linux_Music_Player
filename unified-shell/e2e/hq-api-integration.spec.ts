import { test, expect } from "@playwright/test";

/**
 * 統合フロー E2E テスト: /api/apply → camilladsp --check → 音量復帰
 *
 * 目的:
 * - /api/apply で DSP 設定適用が正常に完了すること
 * - 生成された YAML が camilladsp --check で検証通過すること
 * - 適用後の音量が last_config.volume に復帰すること
 * - DSP 再起動後も音量が維持されること
 */

const HQ_API = process.env.HQ_API_URL || "http://localhost:8002";
const DSP = process.env.DSP_URL || "http://localhost:8000";

test.describe("統合フロー: /api/apply → camilladsp --check → 音量復帰", () => {
  let originalVolume: number;
  let originalConfig: any;

  test.beforeAll(async ({ request }) => {
    // 事前状態保存
    const configRes = await request.get(`${HQ_API}/api/config`);
    originalConfig = await configRes.json();
    originalVolume = originalConfig.volume;
  });

  test.afterAll(async ({ request }) => {
    // 元の設定に復元
    await request.post(`${HQ_API}/api/apply`, {
      data: originalConfig,
    });
  });

  test("基本設定で /api/apply が成功し、YAML が有効", async ({ request }) => {
    const testConfig = {
      mode: "dsp",
      device: "plughw:1,0",
      volume: -10.0,
      music_type: "jazz",
      eq_output: "studio-monitors",
      crossfeed: "light",
      crossfeed_intensity: 50,
      hum_noise: "none",
      reverb: "none",
      reverb_intensity: 5,
    };

    // 1. /api/apply 実行
    const applyRes = await request.post(`${HQ_API}/api/apply`, {
      data: testConfig,
    });
    expect(applyRes.status()).toBe(200);
    const applyJson = await applyRes.json();
    expect(applyJson.status).toBe("success");

    // 2. 生成された YAML が camilladsp --check で有効
    // 注: 実際の camilladsp --check はサーバー側で実行済みだが、
    // ここでは /api/dsp_status で DSP 稼働確認
    await new Promise(r => setTimeout(r, 2000)); // DSP 起動待ち

    const statusRes = await request.get(`${HQ_API}/api/dsp_status`);
    expect(statusRes.status()).toBe(200);
    const statusJson = await statusRes.json();
    expect(statusJson.status).toBe("running");
  });

  test("音量強制復帰: apply 時の volume は無視され last_config.volume が採用される", async ({ request }) => {
    // 1. 現在の last_config.volume を取得
    const configRes1 = await request.get(`${HQ_API}/api/config`);
    const config1 = await configRes1.json();
    const lastVolume = config1.volume;

    // 2. 異なる volume で apply 実行
    const testConfig = {
      mode: "dsp",
      device: "plughw:1,0",
      volume: -20.0, // 異なる値を指定
      music_type: "none",
      eq_output: "none",
      crossfeed: "none",
      crossfeed_intensity: 5,
      hum_noise: "none",
      reverb: "none",
      reverb_intensity: 5,
    };

    const applyRes = await request.post(`${HQ_API}/api/apply`, {
      data: testConfig,
    });
    expect(applyRes.status()).toBe(200);

    // 3. 少し待ってから音量確認
    await new Promise(r => setTimeout(r, 1500));

    const statusRes = await request.get(`${HQ_API}/api/dsp_status`);
    expect(statusRes.status()).toBe(200);

    // 4. /api/config で保存された volume 確認
    const configRes2 = await request.get(`${HQ_API}/api/config`);
    const config2 = await configRes2.json();
    // last_config.volume が採用されているはず
    expect(config2.volume).toBe(lastVolume);
  });

  test("DSP 再起動後も音量が維持される", async ({ request }) => {
    // 1. 現在の volume 取得
    const configRes = await request.get(`${HQ_API}/api/config`);
    const config = await configRes.json();
    const expectedVolume = config.volume;

    // 2. /api/dsp_restart で再起動
    const restartRes = await request.post(`${HQ_API}/api/dsp_restart`, {
      data: config,
    });
    expect(restartRes.status()).toBe(200);

    // 3. DSP 起動待ち
    await new Promise(r => setTimeout(r, 3000));

    // 4. 音量確認
    const statusRes = await request.get(`${HQ_API}/api/dsp_status`);
    expect(statusRes.status()).toBe(200);
    const statusJson = await statusRes.json();
    expect(statusJson.status).toBe("running");

    // 5. 保存された volume 確認
    const configRes2 = await request.get(`${HQ_API}/api/config`);
    const config2 = await configRes2.json();
    expect(config2.volume).toBe(expectedVolume);
  });

  test("dsp_update でパラメータ変更しても音量は維持される", async ({ request }) => {
    // 1. 現在の volume 取得
    const configRes = await request.get(`${HQ_API}/api/config`);
    const config = await configRes.json();
    const expectedVolume = config.volume;

    // 2. dsp_update でパラメータのみ変更
    const updateRes = await request.post(`${HQ_API}/api/dsp_update`, {
      data: {
        music_type: "classical",
        eq_output: "planar-magnetic",
        crossfeed: "standard",
        crossfeed_intensity: 75,
        hum_noise: "50hz",
        reverb: "hall",
        reverb_intensity: 30,
      },
    });
    expect(updateRes.status()).toBe(200);

    // 3. 音量確認
    const configRes2 = await request.get(`${HQ_API}/api/config`);
    const config2 = await configRes2.json();
    expect(config2.volume).toBe(expectedVolume);
  });
});