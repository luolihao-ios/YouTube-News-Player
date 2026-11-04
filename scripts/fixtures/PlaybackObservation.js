(() => {
    'use strict';

    // 仅观察官方页面的标准媒体状态；不控制播放器，也不读取媒体地址或账号数据。
    const video = document.querySelector('video');
    const hasVideo = video !== null;
    const rawTime = hasVideo ? video.currentTime : 0;
    const time = Number.isFinite(rawTime) && rawTime >= 0 ? rawTime : 0;
    const readyState = hasVideo ? video.readyState : 0;
    const playing = hasVideo && !video.paused && !video.ended && readyState >= 2
        && video.videoWidth > 0 && video.videoHeight > 0;
    const mediaError = hasVideo ? video.error : null;

    // 正文只在当前调用内匹配明确提示，返回值不包含任何原文或可见账号。
    const visibleText = document.body ? document.body.innerText : '';
    const verificationRequired = /sign\s+in\s+to\s+confirm|you['’]re\s+not\s+a\s+bot|确认(?:你|您)不是(?:聊天)?机器人|確認(?:你|您)不是(?:聊天)?機器人/i.test(visibleText);
    // 只识别独立提示行，避免把新闻正文里提及的提示文字当作播放器错误。
    const unavailable = !verificationRequired
        && /^\s*(?:video\s+(?:unavailable|(?:is\s+)?not\s+available)|影片無法播放|视频不可用)[.!。！]?\s*$/im.test(visibleText);

    return {
        playing,
        time,
        readyState,
        hasVideo,
        verificationRequired,
        unavailable,
        mediaErrorCode: mediaError ? mediaError.code : null
    };
})();
