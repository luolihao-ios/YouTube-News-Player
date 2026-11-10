import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const sourceURL = new URL('../NewsLiveApp/Resources/PlaybackObservation.js', import.meta.url);
const fields = ['hasVideo', 'mediaErrorCode', 'playing', 'readyState', 'time', 'unavailable', 'verificationRequired'];

// 只模拟标准 DOM 边界；执行真实资源，并记录所有越界读取与写入。
function observe({ video = {}, text = '', bodyMissing = false } = {}) {
  assert.equal(existsSync(sourceURL), true, '实际 WebKit 对照必须提供可执行的只读播放观察脚本');
  const forbidden = [];
  const deny = (label) => {
    forbidden.push(label);
    throw new Error(`禁止访问：${label}`);
  };
  const readonly = (values, label) => new Proxy(values, {
    get(target, key) {
      if (!Object.hasOwn(target, key)) return deny(`${label}.${String(key)}`);
      return target[key];
    },
    set(_target, key) { return deny(`${label}.${String(key)} 写入`); },
    defineProperty(_target, key) { return deny(`${label}.${String(key)} 定义`); },
    deleteProperty(_target, key) { return deny(`${label}.${String(key)} 删除`); },
  });
  const media = video === null ? null : readonly({
    currentTime: 12.5, paused: false, ended: false, readyState: 4,
    videoWidth: 1920, videoHeight: 1080, error: null,
    ...video,
  }, 'video');
  const document = readonly({
    querySelector(selector) {
      if (selector !== 'video') return deny(`querySelector(${selector})`);
      return media;
    },
    body: bodyMissing ? null : readonly({ innerText: text }, 'body'),
  }, 'document');
  const context = { document };
  for (const key of ['window', 'localStorage', 'sessionStorage', 'fetch', 'XMLHttpRequest', 'navigator', 'location']) {
    Object.defineProperty(context, key, { get() { return deny(key); } });
  }
  const result = vm.runInNewContext(readFileSync(sourceURL, 'utf8'), context, { timeout: 1000 });
  assert.deepEqual(forbidden, [], '观察脚本必须只读允许的标准 DOM 字段');
  assert.equal(typeof result, 'object');
  assert.notEqual(result, null);
  const clean = JSON.parse(JSON.stringify(result));
  assert.deepEqual(Object.keys(clean).sort(), fields);
  return clean;
}

test('有画面、已缓冲且正在播放时才报告 playing', () => {
  assert.deepEqual(observe(), {
    playing: true, time: 12.5, readyState: 4, hasVideo: true,
    verificationRequired: false, unavailable: false, mediaErrorCode: null,
  });
});

for (const [name, video] of [
  ['暂停', { paused: true }],
  ['播放结束', { ended: true }],
  ['尚未有数据', { readyState: 0 }],
  ['只有元数据', { readyState: 1 }],
  ['画面宽度为零', { videoWidth: 0 }],
  ['画面高度为零', { videoHeight: 0 }],
]) {
  test(`${name}不能误报正在播放`, () => assert.equal(observe({ video }).playing, false));
}

test('已有当前帧时可以报告正在播放', () => {
  assert.equal(observe({ video: { readyState: 2 } }).playing, true);
});

test('没有 video 或 body 时仍返回完整安全结果', () => {
  assert.deepEqual(observe({ video: null, bodyMissing: true }), {
    playing: false, time: 0, readyState: 0, hasVideo: false,
    verificationRequired: false, unavailable: false, mediaErrorCode: null,
  });
});

for (const value of [NaN, Infinity, -Infinity, -1, undefined, '12']) {
  test(`无效媒体时间 ${String(value)} 归零`, () => {
    assert.equal(observe({ video: { currentTime: value } }).time, 0);
  });
}

test('零时间保持为零', () => assert.equal(observe({ video: { currentTime: 0 } }).time, 0));

for (const text of [
  'Sign in to confirm you’re not a bot',
  "Sign in to confirm you're not a bot",
  "You're not a bot",
  'SIGN IN TO CONFIRM YOUR AGE',
  '登录以确认你不是聊天机器人',
  '请登录，确认您不是机器人',
  '登入以確認你不是聊天機器人',
  '登入以確認您不是機器人',
]) {
  test(`识别官方验证提示：${text}`, () => {
    assert.equal(observe({ text }).verificationRequired, true);
  });
}

for (const text of [
  'Video unavailable',
  'VIDEO IS NOT AVAILABLE',
  'Video is not available.',
  '影片無法播放',
  '视频不可用',
  '视频不可用\n请稍后重试',
]) {
  test(`识别明确不可用提示：${text}`, () => {
    assert.equal(observe({ text }).unavailable, true);
  });
}

test('验证提示优先于不可用提示', () => {
  const result = observe({ text: "Video unavailable\nSign in to confirm you're not a bot" });
  assert.equal(result.verificationRequired, true);
  assert.equal(result.unavailable, false);
});

for (const text of [
  '直播新闻：今天讨论视频播放和帐号问题',
  'The reporter said the video unavailable message appeared yesterday.',
  '新闻字幕提到“视频不可用”提示，但直播仍在播放',
]) {
  test(`普通新闻文字不泛化为错误：${text}`, () => {
    const result = observe({ text });
    assert.equal(result.verificationRequired, false);
    assert.equal(result.unavailable, false);
  });
}

test('读取标准媒体错误码', () => {
  assert.equal(observe({ video: { error: Object.freeze({ code: 3 }) } }).mediaErrorCode, 3);
});

test('正文和可见假帐号不离开页面，仅返回固定字段', () => {
  const text = 'PRIVATE_ACCOUNT_SENTINEL@example.invalid\nSign in to confirm you’re not a bot';
  const result = observe({ text });
  assert.equal(result.verificationRequired, true);
  assert.equal(JSON.stringify(result).includes('PRIVATE_ACCOUNT_SENTINEL'), false);
  assert.equal(JSON.stringify(result).includes('Sign in'), false);
});

test('连续观察不修改视频、DOM、播放器，也不读取媒体地址或账号存储', () => {
  assert.equal(observe().playing, true);
  assert.equal(observe({ video: { paused: true }, text: 'Video unavailable' }).unavailable, true);
});
