import { importShared } from './__federation_fn_import-JrT3xvdd.js';
import Config from './__federation_expose_Config-Cq0FwuDx.js';

true              &&(function polyfill() {
  const relList = document.createElement("link").relList;
  if (relList && relList.supports && relList.supports("modulepreload")) {
    return;
  }
  for (const link of document.querySelectorAll('link[rel="modulepreload"]')) {
    processPreload(link);
  }
  new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type !== "childList") {
        continue;
      }
      for (const node of mutation.addedNodes) {
        if (node.tagName === "LINK" && node.rel === "modulepreload")
          processPreload(node);
      }
    }
  }).observe(document, { childList: true, subtree: true });
  function getFetchOpts(link) {
    const fetchOpts = {};
    if (link.integrity) fetchOpts.integrity = link.integrity;
    if (link.referrerPolicy) fetchOpts.referrerPolicy = link.referrerPolicy;
    if (link.crossOrigin === "use-credentials")
      fetchOpts.credentials = "include";
    else if (link.crossOrigin === "anonymous") fetchOpts.credentials = "omit";
    else fetchOpts.credentials = "same-origin";
    return fetchOpts;
  }
  function processPreload(link) {
    if (link.ep)
      return;
    link.ep = true;
    const fetchOpts = getFetchOpts(link);
    fetch(link.href, fetchOpts);
  }
}());

// 本地预览入口（npm run dev）：用「模拟 host」把 Config.vue 跑起来，不启动平台也能调界面。
// 真正运行时由平台注入真实 host。
const {createApp,h} = await importShared('vue');

let store = {
  cookies: '',
  scan_device: 'alipaymini',
  scan_timeout: 120,
  wxpusher_spt: '',
  notify_on_sign: false,
  checkin_hour: 9,
  checkin_minute: 0,
};

const mockHost = {
  pluginId: 'my115sign',
  token: 'dev',
  async getConfig() { return { ...store } },
  async saveConfig(values) { store = { ...store, ...values }; console.log('[mock] save', store); },
  async callApi(path, opts = {}) {
    console.log('[mock] callApi', path, opts);
    if (path === '/status') return { ok: true, cookie_count: 2, accounts: [{ uid: '12345_1' }, { uid: '67890_1' }], checkin_hour: 9, checkin_minute: 0 }
    if (path === '/sign_now') return { ok: true, message: '115签到(手动)：成功1/已签0/失败0', results: ['[账号 1] ✅ user_id=12345 签到成功 (连续签到=5, 奖励=10)'] }
    if (path === '/cookies') return { ok: true, cookies: [{ uid: '12345_1', cookie: 'UID=12345_1; CID=xxx; SEID=yyy' }, { uid: '67890_1', cookie: 'UID=67890_1; CID=aaa; SEID=bbb' }] }
    if (path === '/delete_cookie') return { ok: true, message: '已删除', count: 1 }
    if (path === '/logs') return { ok: true, logs: [{ t: '09:00:01', m: '[账号 1] ✅ user_id=12345 签到成功 (连续签到=5)' }, { t: '09:00:03', m: '[账号 2] ⚠️ user_id=67890 今日已签到' }] }
    return { ok: true }
  },
  toast: {
    success: (m) => console.log('%c[toast.success] ' + m, 'color:#6ee7a8'),
    error: (m) => console.warn('[toast.error] ' + m),
  },
};

createApp({
  render: () => h(Config, { pluginId: mockHost.pluginId, host: mockHost }),
}).mount('#app');
