import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,vModelText:_vModelText,withDirectives:_withDirectives,renderList:_renderList,Fragment:_Fragment,vModelSelect:_vModelSelect,createTextVNode:_createTextVNode,vModelCheckbox:_vModelCheckbox,vShow:_vShow} = await importShared('vue');


const _hoisted_1 = { class: "sign115" };
const _hoisted_2 = {
  key: 0,
  class: "muted"
};
const _hoisted_3 = { class: "tabs" };
const _hoisted_4 = { class: "pane" };
const _hoisted_5 = { class: "card" };
const _hoisted_6 = { class: "row" };
const _hoisted_7 = { class: "val" };
const _hoisted_8 = { class: "row" };
const _hoisted_9 = { class: "hint" };
const _hoisted_10 = { class: "row" };
const _hoisted_11 = { class: "hint" };
const _hoisted_12 = { class: "card" };
const _hoisted_13 = { class: "row" };
const _hoisted_14 = ["value"];
const _hoisted_15 = { class: "row" };
const _hoisted_16 = { class: "card" };
const _hoisted_17 = { class: "row switch" };
const _hoisted_18 = { class: "row top" };
const _hoisted_19 = { class: "bar" };
const _hoisted_20 = ["disabled"];
const _hoisted_21 = ["disabled"];
const _hoisted_22 = { class: "pane" };
const _hoisted_23 = { class: "toolbar" };
const _hoisted_24 = { class: "muted" };
const _hoisted_25 = {
  key: 0,
  class: "muted center"
};
const _hoisted_26 = {
  key: 1,
  class: "empty"
};
const _hoisted_27 = {
  key: 2,
  class: "acc-list"
};
const _hoisted_28 = { class: "acc-info" };
const _hoisted_29 = { class: "acc-detail" };
const _hoisted_30 = { class: "acc-uid" };
const _hoisted_31 = { class: "acc-sub" };
const _hoisted_32 = ["onClick"];
const _hoisted_33 = { class: "pane" };
const _hoisted_34 = {
  key: 0,
  class: "muted center"
};
const _hoisted_35 = {
  key: 1,
  class: "empty"
};
const _hoisted_36 = {
  key: 2,
  class: "log-list"
};
const _hoisted_37 = { class: "log-time" };
const _hoisted_38 = { class: "log-msg" };

const {ref,reactive,onMounted} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  pluginId: { type: String, required: true },
  host: { type: Object, required: true },
},
  setup(__props) {

// 115签到 · 配置/管理界面（模块联邦暴露为 ./Config）。
// 平台注入 props { pluginId, host }；host: getConfig/saveConfig/callApi/toast。
// 三个页签：配置（签到时间/扫码设备/推送）/ 账号（扫码Cookie列表）/ 日志。
const props = __props;

const DEFAULTS = {
  cookies: '',
  scan_device: 'alipaymini',
  scan_timeout: 120,
  wxpusher_spt: '',
  notify_on_sign: false,
  checkin_hour: 9,
  checkin_minute: 0,
};

const DEVICE_OPTIONS = [
  { value: 'alipaymini', label: '115生活(支付宝小程序)' },
  { value: 'web', label: '网页版' },
  { value: 'android', label: '115生活(Android端)' },
  { value: '115android', label: '115(Android端)' },
  { value: 'ios', label: '115生活(iOS端)' },
  { value: '115ipad', label: '115(iPad端)' },
  { value: 'tv', label: '115网盘(Android电视端)' },
  { value: 'wechatmini', label: '115生活(微信小程序)' },
  { value: 'qandroid', label: '115管理(Android端)' },
  { value: '115ios', label: '115(iOS端)' },
  { value: 'harmony', label: '115(Harmony端)' },
  { value: 'linux', label: 'Linux' },
  { value: 'mac', label: 'Mac' },
  { value: 'windows', label: 'Windows' },
];

const tab = ref('config');
const loading = ref(true);
const saving = ref(false);
const signing = ref(false);
const cfg = reactive({ ...DEFAULTS });

// 账号
const cookies = ref([]);
const accLoading = ref(false);

// 日志
const logs = ref([]);
const logLoading = ref(false);

// 状态
const statusData = ref({});

onMounted(async () => {
  try {
    const saved = await props.host.getConfig();
    Object.assign(cfg, DEFAULTS, saved || {});
  } catch (e) {
    props.host.toast.error('读取配置失败：' + (e.message || e));
  } finally {
    loading.value = false;
  }
});

async function save() {
  saving.value = true;
  try {
    await props.host.saveConfig({ ...cfg });
    props.host.toast.success('配置已保存');
  } catch (e) {
    props.host.toast.error('保存失败：' + (e.message || e));
  } finally {
    saving.value = false;
  }
}

async function signNow() {
  signing.value = true;
  try {
    // 先保存配置再签到
    await props.host.saveConfig({ ...cfg });
    const r = await props.host.callApi('/sign_now', { method: 'POST', body: {} });
    if (r?.ok) {
      props.host.toast.success(r.message || '签到完成');
      // 刷新日志和状态
      await loadLogs();
      await loadStatus();
    } else {
      props.host.toast.error(r?.message || '签到失败');
    }
  } catch (e) {
    props.host.toast.error('签到出错：' + (e.message || e));
  } finally {
    signing.value = false;
  }
}

async function loadStatus() {
  try {
    const r = await props.host.callApi('/status', { method: 'GET' });
    if (r?.ok) {
      statusData.value = r;
    }
  } catch (e) {
    // 静默
  }
}

async function loadCookies() {
  accLoading.value = true;
  try {
    const r = await props.host.callApi('/cookies', { method: 'GET' });
    if (r?.ok) {
      cookies.value = r.cookies || [];
    }
  } catch (e) {
    props.host.toast.error('读取账号失败：' + (e.message || e));
  } finally {
    accLoading.value = false;
  }
}

async function deleteCookie(uid) {
  if (!confirm(`确定删除账号 UID=${uid} 的 Cookie？`)) return
  try {
    const r = await props.host.callApi('/delete_cookie', { method: 'POST', body: { uid } });
    if (r?.ok) {
      props.host.toast.success('已删除');
      await loadCookies();
    } else {
      props.host.toast.error(r?.message || '删除失败');
    }
  } catch (e) {
    props.host.toast.error('删除失败：' + (e.message || e));
  }
}

async function loadLogs() {
  logLoading.value = true;
  try {
    const r = await props.host.callApi('/logs', { method: 'GET' });
    if (r?.ok) {
      logs.value = r.logs || [];
    }
  } catch (e) {
    props.host.toast.error('读取日志失败：' + (e.message || e));
  } finally {
    logLoading.value = false;
  }
}

function switchTab(t) {
  tab.value = t;
  if (t === 'accounts' && !cookies.value.length) loadCookies();
  if (t === 'logs' && !logs.value.length) loadLogs();
}

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (loading.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_2, "加载配置…"))
      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
          _createElementVNode("div", _hoisted_3, [
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'config' }]),
              onClick: _cache[0] || (_cache[0] = $event => (switchTab('config')))
            }, "⚙ 配置", 2),
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'accounts' }]),
              onClick: _cache[1] || (_cache[1] = $event => (switchTab('accounts')))
            }, "📱 账号", 2),
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'logs' }]),
              onClick: _cache[2] || (_cache[2] = $event => (switchTab('logs')))
            }, "📊 日志", 2)
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_4, [
            _createElementVNode("section", _hoisted_5, [
              _cache[12] || (_cache[12] = _createElementVNode("h3", { class: "card-title" }, "⏰ 定时签到", -1)),
              _createElementVNode("div", _hoisted_6, [
                _cache[9] || (_cache[9] = _createElementVNode("span", { class: "lbl" }, "签到时间", -1)),
                _createElementVNode("span", _hoisted_7, _toDisplayString(String(cfg.checkin_hour).padStart(2, '0')) + ":" + _toDisplayString(String(cfg.checkin_minute).padStart(2, '0')), 1)
              ]),
              _createElementVNode("div", _hoisted_8, [
                _cache[10] || (_cache[10] = _createElementVNode("span", { class: "lbl" }, "小时", -1)),
                _withDirectives(_createElementVNode("input", {
                  type: "range",
                  "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.checkin_hour) = $event)),
                  min: "0",
                  max: "23",
                  step: "1",
                  class: "slider"
                }, null, 512), [
                  [
                    _vModelText,
                    cfg.checkin_hour,
                    void 0,
                    { number: true }
                  ]
                ]),
                _createElementVNode("span", _hoisted_9, _toDisplayString(cfg.checkin_hour) + " 时", 1)
              ]),
              _createElementVNode("div", _hoisted_10, [
                _cache[11] || (_cache[11] = _createElementVNode("span", { class: "lbl" }, "分钟", -1)),
                _withDirectives(_createElementVNode("input", {
                  type: "range",
                  "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.checkin_minute) = $event)),
                  min: "0",
                  max: "59",
                  step: "1",
                  class: "slider"
                }, null, 512), [
                  [
                    _vModelText,
                    cfg.checkin_minute,
                    void 0,
                    { number: true }
                  ]
                ]),
                _createElementVNode("span", _hoisted_11, _toDisplayString(cfg.checkin_minute) + " 分", 1)
              ])
            ]),
            _createElementVNode("section", _hoisted_12, [
              _cache[16] || (_cache[16] = _createElementVNode("h3", { class: "card-title" }, "📱 扫码登录", -1)),
              _createElementVNode("div", _hoisted_13, [
                _cache[13] || (_cache[13] = _createElementVNode("span", { class: "lbl" }, "设备类型", -1)),
                _withDirectives(_createElementVNode("select", {
                  "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.scan_device) = $event)),
                  class: "inp"
                }, [
                  (_openBlock(), _createElementBlock(_Fragment, null, _renderList(DEVICE_OPTIONS, (d) => {
                    return _createElementVNode("option", {
                      key: d.value,
                      value: d.value
                    }, _toDisplayString(d.label), 9, _hoisted_14)
                  }), 64))
                ], 512), [
                  [_vModelSelect, cfg.scan_device]
                ])
              ]),
              _createElementVNode("div", _hoisted_15, [
                _cache[14] || (_cache[14] = _createElementVNode("span", { class: "lbl" }, "扫码超时", -1)),
                _withDirectives(_createElementVNode("input", {
                  "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.scan_timeout) = $event)),
                  class: "inp sm",
                  type: "number",
                  min: "30",
                  max: "300"
                }, null, 512), [
                  [
                    _vModelText,
                    cfg.scan_timeout,
                    void 0,
                    { number: true }
                  ]
                ]),
                _cache[15] || (_cache[15] = _createElementVNode("span", { class: "hint" }, "秒（30~300）", -1))
              ]),
              _cache[17] || (_cache[17] = _createElementVNode("p", { class: "tip" }, [
                _createTextVNode("💡 扫码登录请在聊天中发送 "),
                _createElementVNode("code", null, ".115login"),
                _createTextVNode("，选择设备后用 115 APP 扫码。推荐使用「115生活(支付宝小程序)」，Cookie 不易失效。")
              ], -1))
            ]),
            _createElementVNode("section", _hoisted_16, [
              _cache[20] || (_cache[20] = _createElementVNode("h3", { class: "card-title" }, "🔔 推送通知", -1)),
              _createElementVNode("label", _hoisted_17, [
                _withDirectives(_createElementVNode("input", {
                  "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.notify_on_sign) = $event)),
                  type: "checkbox"
                }, null, 512), [
                  [_vModelCheckbox, cfg.notify_on_sign]
                ]),
                _cache[18] || (_cache[18] = _createElementVNode("span", null, "WxPusher 推送签到结果", -1))
              ]),
              _cache[21] || (_cache[21] = _createElementVNode("p", { class: "tip" }, "开启后，签到结果会推送到 WxPusher（需配置下方 SPT）。平台内通知（TG/飞书）始终发送，不受此开关控制。", -1)),
              _createElementVNode("div", _hoisted_18, [
                _cache[19] || (_cache[19] = _createElementVNode("span", { class: "lbl" }, "WxPusher SPT", -1)),
                _withDirectives(_createElementVNode("textarea", {
                  "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.wxpusher_spt) = $event)),
                  class: "inp",
                  rows: "2",
                  placeholder: "WxPusher 推送令牌，留空则不推送。多个用逗号或换行分隔。"
                }, null, 512), [
                  [_vModelText, cfg.wxpusher_spt]
                ])
              ])
            ]),
            _createElementVNode("div", _hoisted_19, [
              _createElementVNode("button", {
                class: "btn primary",
                disabled: signing.value,
                onClick: signNow
              }, _toDisplayString(signing.value ? '签到中…' : '▶ 立即签到'), 9, _hoisted_20),
              _createElementVNode("button", {
                class: "btn",
                disabled: saving.value,
                onClick: save
              }, _toDisplayString(saving.value ? '保存中…' : '💾 保存配置'), 9, _hoisted_21)
            ])
          ], 512), [
            [_vShow, tab.value === 'config']
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_22, [
            _createElementVNode("div", _hoisted_23, [
              _createElementVNode("span", _hoisted_24, "扫码登录的账号（共 " + _toDisplayString(cookies.value.length) + " 个）", 1),
              _cache[22] || (_cache[22] = _createElementVNode("span", { class: "grow" }, null, -1)),
              _createElementVNode("button", {
                class: "btn",
                onClick: loadCookies
              }, "🔄 刷新")
            ]),
            (accLoading.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_25, "加载中…"))
              : (!cookies.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_26, [...(_cache[23] || (_cache[23] = [
                    _createTextVNode(" 暂无扫码登录的账号", -1),
                    _createElementVNode("br", null, null, -1),
                    _createElementVNode("span", { class: "muted" }, [
                      _createTextVNode("扫码登录请在聊天中发送 "),
                      _createElementVNode("code", null, ".115login")
                    ], -1)
                  ]))]))
                : (_openBlock(), _createElementBlock("div", _hoisted_27, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(cookies.value, (c, i) => {
                      return (_openBlock(), _createElementBlock("div", {
                        key: i,
                        class: "acc-card"
                      }, [
                        _createElementVNode("div", _hoisted_28, [
                          _cache[24] || (_cache[24] = _createElementVNode("span", { class: "acc-icon" }, "👤", -1)),
                          _createElementVNode("div", _hoisted_29, [
                            _createElementVNode("div", _hoisted_30, "UID: " + _toDisplayString(c.uid), 1),
                            _createElementVNode("div", _hoisted_31, "扫码登录账号 #" + _toDisplayString(i + 1), 1)
                          ])
                        ]),
                        _createElementVNode("button", {
                          class: "btn sm danger",
                          onClick: $event => (deleteCookie(c.uid))
                        }, "删除", 8, _hoisted_32)
                      ]))
                    }), 128))
                  ])),
            _cache[25] || (_cache[25] = _createElementVNode("div", { class: "hint-box" }, [
              _createTextVNode(" 💡 扫码登录请在聊天中发送 "),
              _createElementVNode("code", null, ".115login"),
              _createTextVNode("，选择设备后用 115 APP 扫码即可自动添加 Cookie。 ")
            ], -1))
          ], 512), [
            [_vShow, tab.value === 'accounts']
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_33, [
            _createElementVNode("div", { class: "toolbar" }, [
              _cache[26] || (_cache[26] = _createElementVNode("span", { class: "muted" }, "运行日志", -1)),
              _cache[27] || (_cache[27] = _createElementVNode("span", { class: "grow" }, null, -1)),
              _createElementVNode("button", {
                class: "btn",
                onClick: loadLogs
              }, "🔄 刷新")
            ]),
            (logLoading.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_34, "加载中…"))
              : (!logs.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_35, [...(_cache[28] || (_cache[28] = [
                    _createTextVNode(" 暂无日志", -1),
                    _createElementVNode("br", null, null, -1),
                    _createElementVNode("span", { class: "muted" }, "签到后日志会在这里显示", -1)
                  ]))]))
                : (_openBlock(), _createElementBlock("div", _hoisted_36, [
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(logs.value, (log, i) => {
                      return (_openBlock(), _createElementBlock("div", {
                        key: i,
                        class: "log-item"
                      }, [
                        _createElementVNode("span", _hoisted_37, _toDisplayString(log.t), 1),
                        _createElementVNode("span", _hoisted_38, _toDisplayString(log.m), 1)
                      ]))
                    }), 128))
                  ]))
          ], 512), [
            [_vShow, tab.value === 'logs']
          ])
        ], 64))
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-bb1fa1d6"]]);

export { Config as default };
