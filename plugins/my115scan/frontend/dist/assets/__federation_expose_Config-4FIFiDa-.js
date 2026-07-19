import { importShared } from './__federation_fn_import-GzAXfPDJ.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,vModelText:_vModelText,withDirectives:_withDirectives,vModelCheckbox:_vModelCheckbox,renderList:_renderList,Fragment:_Fragment,openBlock:_openBlock,createElementBlock:_createElementBlock,toDisplayString:_toDisplayString,vShow:_vShow,createCommentVNode:_createCommentVNode} = await importShared('vue');


const _hoisted_1 = { class: "mm" };
const _hoisted_2 = { class: "tabs" };
const _hoisted_3 = { class: "layout" };
const _hoisted_4 = { class: "card" };
const _hoisted_5 = { class: "row" };
const _hoisted_6 = { class: "row" };
const _hoisted_7 = { class: "card" };
const _hoisted_8 = { class: "row" };
const _hoisted_9 = { class: "row" };
const _hoisted_10 = { class: "row switch" };
const _hoisted_11 = { class: "card" };
const _hoisted_12 = { class: "row" };
const _hoisted_13 = { class: "row" };
const _hoisted_14 = { class: "row switch" };
const _hoisted_15 = { class: "card" };
const _hoisted_16 = { class: "row" };
const _hoisted_17 = { class: "card" };
const _hoisted_18 = { class: "genre-grid" };
const _hoisted_19 = ["onClick"];
const _hoisted_20 = { class: "card" };
const _hoisted_21 = { class: "row" };
const _hoisted_22 = { class: "row" };
const _hoisted_23 = { class: "row" };
const _hoisted_24 = { class: "row" };
const _hoisted_25 = {
  class: "row",
  style: {"gap":"8px"}
};
const _hoisted_26 = ["disabled"];
const _hoisted_27 = ["disabled"];
const _hoisted_28 = { class: "savebar" };
const _hoisted_29 = ["disabled"];
const _hoisted_30 = { class: "pane" };
const _hoisted_31 = { class: "card" };
const _hoisted_32 = { class: "kv" };
const _hoisted_33 = { class: "kv" };
const _hoisted_34 = { class: "kv" };
const _hoisted_35 = ["disabled"];
const _hoisted_36 = { class: "pane" };
const _hoisted_37 = { class: "toolbar" };
const _hoisted_38 = { class: "muted" };
const _hoisted_39 = {
  key: 0,
  class: "tbl"
};
const _hoisted_40 = { class: "muted" };
const _hoisted_41 = {
  key: 1,
  class: "empty muted"
};

const {ref,reactive,computed,onMounted} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: { pluginId: String, host: Object },
  setup(__props) {

const props = __props;
const tab = ref('settings');
const saving = ref(false);
const testing = ref(false);
const s = reactive({});
const testMsg = ref('');
const testOk = ref(false);
const logs = ref([]);
const cfg = reactive({
  media_types: ['movie', 'tv'], only_complete_series: false,
  tmdb_api_key: '', tmdb_language: 'zh-CN',
  emby_url: '', emby_api_key: '', skip_emby_check: false,
  cms_bot_username: '', forward_label: '115 网盘', forward_to_saved: false,
  pan115_cookie: '',
  exclude_genres: '',
  source_chat: 0,
  delay: 2,
  batch_size: 200,
});

computed({
  get: () => Array.isArray(cfg.media_types) ? cfg.media_types : [],
  set: (v) => { cfg.media_types = v; },
});

onMounted(async () => {
  try {
    const saved = await props.host.getConfig();
    Object.assign(cfg, saved || {});
  } catch (e) {
    props.host.toast.error('读取配置失败：' + (e.message || e));
  }
});

const genreList = [
  { en: 'animation:cn', cn: '国漫' },
  { en: 'animation:jp', cn: '日漫' },
  { en: 'animation:us', cn: '美漫' },
  { en: 'animation:other', cn: '其他动画' },
  { en: 'comedy', cn: '喜剧' },
  { en: 'documentary', cn: '纪录片' },
  { en: 'drama', cn: '剧情' },
  { en: 'action', cn: '动作' },
  { en: 'adventure', cn: '冒险' },
  { en: 'fantasy', cn: '奇幻' },
  { en: 'science fiction', cn: '科幻' },
  { en: 'horror', cn: '恐怖' },
  { en: 'thriller', cn: '惊悚' },
  { en: 'romance', cn: '爱情' },
  { en: 'mystery', cn: '悬疑' },
  { en: 'crime', cn: '犯罪' },
  { en: 'war', cn: '战争' },
  { en: 'western', cn: '西部' },
  { en: 'history', cn: '历史' },
  { en: 'music', cn: '音乐' },
  { en: 'family', cn: '家庭' },
  { en: 'kids', cn: '儿童' },
  { en: 'reality', cn: '真人秀' },
  { en: 'soap', cn: '肥皂剧' },
  { en: 'talk', cn: '脱口秀' },
  { en: 'news', cn: '新闻' },
];
const excludeSet = computed(() => {
  const raw = (cfg.exclude_genres || '').toLowerCase();
  return new Set(raw.split(',').map(s => s.trim()).filter(Boolean))
});
function toggleGenre(g) {
  const raw = (cfg.exclude_genres || '').trim();
  const arr = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : [];
  const key = g.en.toLowerCase();
  const i = arr.indexOf(key);
  if (i >= 0) arr.splice(i, 1); else arr.push(key);
  cfg.exclude_genres = arr.join(',');
}

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

async function loadStatus() {
  try {
    const r = await props.host.callApi('/status');
    Object.assign(s, r || {});
  } catch {}
}

async function testServices() {
  testing.value = true; testMsg.value = '';
  try {
    const r = await props.host.callApi('/test', { method: 'POST', body: {} });
    testOk.value = r.ok; testMsg.value = r.message || '';
    await loadStatus();
  } catch (e) {
    testOk.value = false; testMsg.value = e.message || '测试失败';
  } finally { testing.value = false; }
}


const scanning = ref(false);
const scanStatus = ref('就绪');

async function startScan() {
  scanning.value = true; scanStatus.value = '扫描中…';
  try {
    const r = await props.host.callApi('/start_scan', { method: 'POST' });
    if (!r.ok) { scanStatus.value = r.message || '启动失败'; scanning.value = false; }
  } catch (e) { scanStatus.value = e.message || '启动失败'; scanning.value = false; }
}
async function stopScan() {
  await props.host.callApi('/stop_scan', { method: 'POST' });
  scanning.value = false; scanStatus.value = '已停止';
}
async function resetScan() {
  await props.host.callApi('/reset_scan', { method: 'POST' });
  scanning.value = false; scanStatus.value = '已重置';
}
onMounted(() => {
  setInterval(async () => {
    try {
      const r = await props.host.callApi('/scan_status');
      if (r) {
        scanStatus.value = r.status || '就绪';
        scanning.value = r.running || false;
      }
    } catch {}
  }, 5000);
});

async function loadLogs() {
  try {
    const r = await props.host.callApi('/logs');
    logs.value = (r && r.logs) || [];
  } catch {}
}

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _createElementVNode("button", {
        class: _normalizeClass(['tab', { on: tab.value === 'settings' }]),
        onClick: _cache[0] || (_cache[0] = $event => (tab.value = 'settings'))
      }, "⚙ 设置", 2),
      _createElementVNode("button", {
        class: _normalizeClass(['tab', { on: tab.value === 'status' }]),
        onClick: _cache[1] || (_cache[1] = $event => {loadStatus(); tab.value = 'status';})
      }, "📊 状态", 2),
      _createElementVNode("button", {
        class: _normalizeClass(['tab', { on: tab.value === 'logs' }]),
        onClick: _cache[2] || (_cache[2] = $event => {loadLogs(); tab.value = 'logs';})
      }, "📝 记录", 2)
    ]),
    _withDirectives(_createElementVNode("div", _hoisted_3, [
      _createElementVNode("section", _hoisted_4, [
        _cache[17] || (_cache[17] = _createElementVNode("h3", null, "TMDB", -1)),
        _createElementVNode("label", _hoisted_5, [
          _cache[15] || (_cache[15] = _createElementVNode("span", null, "API Key", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.tmdb_api_key) = $event)),
            class: "inp",
            type: "password",
            placeholder: "必填"
          }, null, 512), [
            [_vModelText, cfg.tmdb_api_key]
          ])
        ]),
        _createElementVNode("label", _hoisted_6, [
          _cache[16] || (_cache[16] = _createElementVNode("span", null, "语言", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.tmdb_language) = $event)),
            class: "inp",
            placeholder: "zh-CN"
          }, null, 512), [
            [_vModelText, cfg.tmdb_language]
          ])
        ])
      ]),
      _createElementVNode("section", _hoisted_7, [
        _cache[21] || (_cache[21] = _createElementVNode("h3", null, "Emby", -1)),
        _createElementVNode("label", _hoisted_8, [
          _cache[18] || (_cache[18] = _createElementVNode("span", null, "地址", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.emby_url) = $event)),
            class: "inp",
            placeholder: "http://emby.local:8096"
          }, null, 512), [
            [_vModelText, cfg.emby_url]
          ])
        ]),
        _createElementVNode("label", _hoisted_9, [
          _cache[19] || (_cache[19] = _createElementVNode("span", null, "API Key", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.emby_api_key) = $event)),
            class: "inp",
            type: "password"
          }, null, 512), [
            [_vModelText, cfg.emby_api_key]
          ])
        ]),
        _createElementVNode("label", _hoisted_10, [
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.skip_emby_check) = $event)),
            type: "checkbox"
          }, null, 512), [
            [_vModelCheckbox, cfg.skip_emby_check]
          ]),
          _cache[20] || (_cache[20] = _createElementVNode("span", null, "跳过 Emby 查重", -1))
        ])
      ]),
      _createElementVNode("section", _hoisted_11, [
        _cache[25] || (_cache[25] = _createElementVNode("h3", null, "转发", -1)),
        _createElementVNode("label", _hoisted_12, [
          _cache[22] || (_cache[22] = _createElementVNode("span", null, "目标", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.cms_bot_username) = $event)),
            class: "inp",
            placeholder: "如 @cmsbot 或 me"
          }, null, 512), [
            [_vModelText, cfg.cms_bot_username]
          ])
        ]),
        _createElementVNode("label", _hoisted_13, [
          _cache[23] || (_cache[23] = _createElementVNode("span", null, "标签", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.forward_label) = $event)),
            class: "inp",
            placeholder: "115 网盘"
          }, null, 512), [
            [_vModelText, cfg.forward_label]
          ])
        ]),
        _createElementVNode("label", _hoisted_14, [
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.forward_to_saved) = $event)),
            type: "checkbox"
          }, null, 512), [
            [_vModelCheckbox, cfg.forward_to_saved]
          ]),
          _cache[24] || (_cache[24] = _createElementVNode("span", null, "转发到收藏夹", -1))
        ])
      ]),
      _createElementVNode("section", _hoisted_15, [
        _cache[27] || (_cache[27] = _createElementVNode("h3", null, "115 网盘", -1)),
        _createElementVNode("label", _hoisted_16, [
          _cache[26] || (_cache[26] = _createElementVNode("span", null, "Cookie", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.pan115_cookie) = $event)),
            class: "inp",
            type: "password",
            placeholder: "可选"
          }, null, 512), [
            [_vModelText, cfg.pan115_cookie]
          ])
        ])
      ]),
      _createElementVNode("section", _hoisted_17, [
        _cache[28] || (_cache[28] = _createElementVNode("h3", null, "排除类型", -1)),
        _cache[29] || (_cache[29] = _createElementVNode("p", { class: "tip" }, "勾选后匹配到该类型的资源自动跳过不转发。动画按产地细分：国漫/日漫/美漫/其他，国语配音的国外动画不会误杀。", -1)),
        _createElementVNode("div", _hoisted_18, [
          (_openBlock(), _createElementBlock(_Fragment, null, _renderList(genreList, (g) => {
            return _createElementVNode("div", {
              key: g.en,
              class: _normalizeClass(["chip", { on: excludeSet.value.has(g.en.toLowerCase()) }]),
              onClick: $event => (toggleGenre(g))
            }, [
              _createElementVNode("span", null, _toDisplayString(g.cn), 1)
            ], 10, _hoisted_19)
          }), 64))
        ])
      ]),
      _createElementVNode("section", _hoisted_20, [
        _cache[34] || (_cache[34] = _createElementVNode("h3", null, "📡 历史扫描", -1)),
        _createElementVNode("label", _hoisted_21, [
          _cache[30] || (_cache[30] = _createElementVNode("span", null, "来源频道", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.source_chat) = $event)),
            class: "inp",
            type: "number",
            placeholder: "频道ID"
          }, null, 512), [
            [_vModelText, cfg.source_chat]
          ])
        ]),
        _createElementVNode("label", _hoisted_22, [
          _cache[31] || (_cache[31] = _createElementVNode("span", null, "间隔(秒)", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.delay) = $event)),
            class: "inp",
            type: "number",
            placeholder: "2"
          }, null, 512), [
            [_vModelText, cfg.delay]
          ])
        ]),
        _createElementVNode("label", _hoisted_23, [
          _cache[32] || (_cache[32] = _createElementVNode("span", null, "每批条数", -1)),
          _withDirectives(_createElementVNode("input", {
            "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.batch_size) = $event)),
            class: "inp",
            type: "number",
            placeholder: "200"
          }, null, 512), [
            [_vModelText, cfg.batch_size]
          ])
        ]),
        _createElementVNode("div", _hoisted_24, [
          _cache[33] || (_cache[33] = _createElementVNode("span", null, "状态", -1)),
          _createElementVNode("b", null, _toDisplayString(scanStatus.value), 1)
        ]),
        _createElementVNode("div", _hoisted_25, [
          _createElementVNode("button", {
            class: "btn primary",
            disabled: scanning.value,
            onClick: startScan
          }, "▶ 开始扫描", 8, _hoisted_26),
          _createElementVNode("button", {
            class: "btn",
            disabled: !scanning.value,
            onClick: stopScan
          }, "⏹ 停止", 8, _hoisted_27),
          _createElementVNode("button", {
            class: "btn",
            onClick: resetScan
          }, "🔄 重置")
        ])
      ]),
      _createElementVNode("div", _hoisted_28, [
        _createElementVNode("button", {
          class: "btn primary lg",
          disabled: saving.value,
          onClick: save
        }, _toDisplayString(saving.value ? '保存中…' : '保存配置'), 9, _hoisted_29)
      ])
    ], 512), [
      [_vShow, tab.value === 'settings']
    ]),
    _withDirectives(_createElementVNode("div", _hoisted_30, [
      _createElementVNode("div", _hoisted_31, [
        _createElementVNode("div", _hoisted_32, [
          _cache[35] || (_cache[35] = _createElementVNode("span", null, "TMDB", -1)),
          _createElementVNode("b", {
            class: _normalizeClass(s.tmdb_ok ? 'ok' : 'err')
          }, _toDisplayString(s.tmdb_status || '未检测'), 3)
        ]),
        _createElementVNode("div", _hoisted_33, [
          _cache[36] || (_cache[36] = _createElementVNode("span", null, "Emby", -1)),
          _createElementVNode("b", {
            class: _normalizeClass(s.emby_ok ? 'ok' : 'err')
          }, _toDisplayString(s.emby_status || '未检测'), 3)
        ]),
        _createElementVNode("div", _hoisted_34, [
          _cache[37] || (_cache[37] = _createElementVNode("span", null, "Emby 库", -1)),
          _createElementVNode("b", null, _toDisplayString(s.emby_items ?? '-') + " 项", 1)
        ])
      ]),
      _createElementVNode("button", {
        class: "btn",
        disabled: testing.value,
        onClick: testServices
      }, _toDisplayString(testing.value ? '测试中…' : '测试连接'), 9, _hoisted_35),
      (testMsg.value)
        ? (_openBlock(), _createElementBlock("p", {
            key: 0,
            class: _normalizeClass(['test-msg', testOk.value ? 'ok' : 'err'])
          }, _toDisplayString(testMsg.value), 3))
        : _createCommentVNode("", true)
    ], 512), [
      [_vShow, tab.value === 'status']
    ]),
    _withDirectives(_createElementVNode("div", _hoisted_36, [
      _createElementVNode("div", _hoisted_37, [
        _createElementVNode("button", {
          class: "btn",
          onClick: loadLogs
        }, "刷新"),
        _createElementVNode("span", _hoisted_38, _toDisplayString(logs.value.length) + " 条", 1)
      ]),
      (logs.value.length)
        ? (_openBlock(), _createElementBlock("table", _hoisted_39, [
            _cache[38] || (_cache[38] = _createElementVNode("thead", null, [
              _createElementVNode("tr", null, [
                _createElementVNode("th", null, "时间"),
                _createElementVNode("th", null, "标题"),
                _createElementVNode("th", null, "TMDB"),
                _createElementVNode("th", null, "操作")
              ])
            ], -1)),
            _createElementVNode("tbody", null, [
              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(logs.value, (l, i) => {
                return (_openBlock(), _createElementBlock("tr", { key: i }, [
                  _createElementVNode("td", _hoisted_40, _toDisplayString(l.time), 1),
                  _createElementVNode("td", null, _toDisplayString(l.title), 1),
                  _createElementVNode("td", null, [
                    _createElementVNode("code", null, _toDisplayString(l.tmdb_id || '-'), 1)
                  ]),
                  _createElementVNode("td", null, [
                    _createElementVNode("span", {
                      class: _normalizeClass('tag-' + l.action)
                    }, _toDisplayString(l.action), 3)
                  ])
                ]))
              }), 128))
            ])
          ]))
        : (_openBlock(), _createElementBlock("div", _hoisted_41, "暂无处理记录"))
    ], 512), [
      [_vShow, tab.value === 'logs']
    ])
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f10c1dd7"]]);

export { Config as default };
