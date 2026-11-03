import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

// 使用真正随 App 打包的脚本，模拟的仅是 WebKit 和官方播放器边界。
function harness(config = {videoID:'abcdefghijk',origin:'https://app.example.newslive'}) {
  const file = new URL('../NewsLiveApp/Resources/YouTubePlayer.html', import.meta.url);
  assert.ok(fs.existsSync(file), 'App 尚未实现播放器 HTML');
  const html = fs.readFileSync(file,'utf8');
  const scripts = [...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
  assert.equal(scripts.length,1);
  const messages=[], calls=[];
  let options;
  const context = {
    window:{webkit:{messageHandlers:{youtube:{postMessage:m=>messages.push(m)}}}},
    document:{hidden:false,addEventListener:(name,fn)=>{context[name]=fn;}},
    YT:{Player:function(id,opts){options=opts;return {pauseVideo:()=>calls.push('pause'),destroy:()=>calls.push('destroy')};}},
    URL, console
  };
  vm.createContext(context);
  vm.runInContext(scripts[0].replace('__PLAYER_CONFIGURATION__',JSON.stringify(config)),context);
  return {context,messages,calls,get options(){return options;},html};
}

test('官方 API 初始化：不隐藏控件、不自动播放并提供 origin',()=>{
  const h=harness();h.context.onYouTubeIframeAPIReady();
  assert.equal(h.options.videoId,'abcdefghijk');
  assert.equal(h.options.playerVars.controls,1);
  assert.equal(h.options.playerVars.autoplay,0);
  assert.equal(h.options.playerVars.playsinline,1);
  assert.equal(h.options.playerVars.origin,'https://app.example.newslive');
  assert.match(h.html,/https:\/\/www\.youtube\.com\/iframe_api/);
  assert.match(h.html,/strict-origin-when-cross-origin/);
});
test('非法 video ID 不传入播放器',()=>{
  const h=harness({videoID:'bad<script>',origin:'https://app.example.newslive'});
  h.context.onYouTubeIframeAPIReady();assert.equal(h.options,undefined);
  assert.equal(h.messages[0].type,'error');assert.equal(h.messages[0].code,2);
});
test('官方错误码和已结束状态传给原生层',()=>{
  const h=harness();h.context.onYouTubeIframeAPIReady();
  for(const code of [100,101,150,153]) h.options.events.onError({data:code});
  h.options.events.onStateChange({data:0});
  assert.deepEqual(h.messages.map(m=>m.code),[100,101,150,153,undefined]);
  assert.equal(h.messages.at(-1).state,0);
});
test('切后台、原生命令和销毁暂停视频',()=>{
  const h=harness();h.context.onYouTubeIframeAPIReady();
  h.context.window.NewsPlayer.pause();
  h.context.document.hidden=true;h.context.visibilitychange();
  h.context.window.NewsPlayer.destroy();
  assert.deepEqual(h.calls,['pause','pause','pause','destroy']);
});
test('未初始化时暂停或销毁不崩溃',()=>{
  const h=harness();assert.doesNotThrow(()=>h.context.window.NewsPlayer.pause());
  assert.doesNotThrow(()=>h.context.window.NewsPlayer.destroy());
});
