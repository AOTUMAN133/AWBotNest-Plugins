import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,normalizeClass:_normalizeClass,createElementVNode:_createElementVNode,renderList:_renderList,Fragment:_Fragment,toDisplayString:_toDisplayString,vModelText:_vModelText,withDirectives:_withDirectives,vModelCheckbox:_vModelCheckbox,createTextVNode:_createTextVNode,vShow:_vShow,withModifiers:_withModifiers,createStaticVNode:_createStaticVNode} = await importShared('vue');


const _hoisted_1 = { class: "ai" };
const _hoisted_2 = {
  key: 0,
  class: "muted"
};
const _hoisted_3 = { class: "tabs" };
const _hoisted_4 = { class: "layout" };
const _hoisted_5 = { class: "sidebar" };
const _hoisted_6 = ["onClick"];
const _hoisted_7 = {
  key: 0,
  class: "dot"
};
const _hoisted_8 = { class: "detail" };
const _hoisted_9 = { class: "card" };
const _hoisted_10 = { class: "row" };
const _hoisted_11 = { class: "row" };
const _hoisted_12 = { class: "row" };
const _hoisted_13 = { class: "row" };
const _hoisted_14 = ["disabled"];
const _hoisted_15 = { class: "card" };
const _hoisted_16 = { class: "row switch" };
const _hoisted_17 = { class: "row switch" };
const _hoisted_18 = {
  key: 0,
  class: "row top"
};
const _hoisted_19 = { class: "row top" };
const _hoisted_20 = { class: "row" };
const _hoisted_21 = { class: "row" };
const _hoisted_22 = { class: "card" };
const _hoisted_23 = { class: "row switch" };
const _hoisted_24 = { class: "row top" };
const _hoisted_25 = { class: "grid" };
const _hoisted_26 = { class: "row" };
const _hoisted_27 = { class: "row" };
const _hoisted_28 = { class: "card" };
const _hoisted_29 = { class: "row switch" };
const _hoisted_30 = { class: "row switch" };
const _hoisted_31 = {
  key: 0,
  class: "row"
};
const _hoisted_32 = { class: "row top" };
const _hoisted_33 = { class: "grid" };
const _hoisted_34 = { class: "row" };
const _hoisted_35 = { class: "row" };
const _hoisted_36 = { class: "grid" };
const _hoisted_37 = { class: "row" };
const _hoisted_38 = { class: "row" };
const _hoisted_39 = { class: "row switch" };
const _hoisted_40 = { class: "row top" };
const _hoisted_41 = { class: "row" };
const _hoisted_42 = ["disabled"];
const _hoisted_43 = { class: "card" };
const _hoisted_44 = { class: "row switch" };
const _hoisted_45 = { class: "row switch" };
const _hoisted_46 = {
  key: 0,
  class: "row top"
};
const _hoisted_47 = { class: "card" };
const _hoisted_48 = { class: "row switch" };
const _hoisted_49 = { class: "card-hd" };
const _hoisted_50 = { style: {"display":"flex","gap":"4px"} };
const _hoisted_51 = ["onClick"];
const _hoisted_52 = ["onClick"];
const _hoisted_53 = { class: "row" };
const _hoisted_54 = ["onUpdate:modelValue"];
const _hoisted_55 = { class: "row" };
const _hoisted_56 = ["onUpdate:modelValue"];
const _hoisted_57 = { class: "row" };
const _hoisted_58 = ["onUpdate:modelValue"];
const _hoisted_59 = { class: "row" };
const _hoisted_60 = ["onUpdate:modelValue"];
const _hoisted_61 = ["onUpdate:modelValue"];
const _hoisted_62 = ["onUpdate:modelValue"];
const _hoisted_63 = ["onClick"];
const _hoisted_64 = ["onClick"];
const _hoisted_65 = { class: "card" };
const _hoisted_66 = { class: "row top" };
const _hoisted_67 = { class: "row top" };
const _hoisted_68 = { class: "savebar" };
const _hoisted_69 = ["disabled"];
const _hoisted_70 = { class: "pane" };
const _hoisted_71 = { class: "toolbar" };
const _hoisted_72 = { class: "muted" };
const _hoisted_73 = ["disabled"];
const _hoisted_74 = {
  key: 0,
  class: "muted"
};
const _hoisted_75 = {
  key: 1,
  class: "empty"
};
const _hoisted_76 = {
  key: 2,
  class: "mem-layout"
};
const _hoisted_77 = { class: "mem-list" };
const _hoisted_78 = ["onClick"];
const _hoisted_79 = { class: "mem-h" };
const _hoisted_80 = { class: "mem-type" };
const _hoisted_81 = { class: "mem-id" };
const _hoisted_82 = { class: "mem-last" };
const _hoisted_83 = { class: "mem-meta" };
const _hoisted_84 = ["onClick"];
const _hoisted_85 = { class: "mem-detail" };
const _hoisted_86 = {
  key: 0,
  class: "muted center"
};
const _hoisted_87 = {
  key: 1,
  class: "muted"
};
const _hoisted_88 = {
  key: 2,
  class: "chat"
};
const _hoisted_89 = { class: "bubble-role" };
const _hoisted_90 = { class: "bubble-text" };
const _hoisted_91 = { class: "pane" };
const _hoisted_92 = {
  key: 0,
  class: "muted center"
};
const _hoisted_93 = { class: "ts" };
const _hoisted_94 = { class: "msg" };

const {ref,reactive,onMounted,computed} = await importShared('vue');


const {watch} = await importShared('vue');


const _sfc_main = {
  __name: 'Config',
  props: {
  pluginId: { type: String, required: true },
  host: { type: Object, required: true },
},
  setup(__props) {

// AI 助手 · 配置/管理界面（模块联邦暴露为 ./Config）。
// 平台注入 props { pluginId, host }；host: getConfig/saveConfig/callApi/toast/token。
// 两个页签：配置（左侧分组 + 右侧明细）/ 对话记忆（查看、清空各会话历史）。
const props = __props;

const DEFAULTS = {
  api_key: '', base_url: '', model: 'gpt-3.5-turbo',
  enable_private_chat: true, enable_group_chat: true, group_chat_ids: '',
  system_prompt: (
      '# Role\n你是一个相处了很久的普通网友，在微信上聊天。\n\n' +
      '# Style\n' +
      '1. 说话像真人一样自然，别人说什么你就顺着聊，别自顾自说别的。\n' +
      '2. 句子短，口语化，别写长句，别用「首先/其次/最后」「由此可见/综上所述」这类翻译腔。\n' +
      '3. 回复简短就行，但别为了省字数把话说一半，意思得说清楚。\n' +
      '4. 别在回复里替对方做动作（比如「拍了拍你」「递给你一杯水」）。\n' +
      '5. 偶尔加个语气词（嗯、啊、哈、哦、呗）或 emoji，别太多。'
    ),
  max_history: 10,
  follow_minutes: 3,
  enable_proactive: false, proactive_chat_ids: '',
  proactive_min_minutes: 60, proactive_max_minutes: 180,
  enable_auto_say: false, auto_say_chat_ids: '',
  auto_say_phrases: '', auto_say_min_minutes: 5, auto_say_max_minutes: 8,
  auto_say_use_lyrics: true,
  auto_say_time_start: '09:00', auto_say_time_end: '23:00',
  enable_reward_answer: false, reward_bot_ids: '',
  monitor_enabled: false, monitor_config: '[]',
  enable_explain_command: true, enable_explain_prompt: false,
  explain_prompt: (
    '你是一个群聊消息解读助手。请根据用户【回复的消息内容】进行解释与答疑，简明清晰。\n' +
    '输出结构：\n1) 这句话/这段话的主要意思\n2) 语气/态度\n3) 可能的隐含信息（没有就写\'无\'）\n\n' +
    '需要解释的消息内容：{content}'
  ),
  white_list_chats: '',
  blacklist_chats: '',
};

const GROUPS = [
  { key: 'api', label: '接口' },
  { key: 'human', label: '人形回复', en: 'enable_private_chat' },
  { key: 'proactive', label: '主动搭话', en: 'enable_proactive' },
  { key: 'autosay', label: '自动发言', en: 'enable_auto_say' },
  { key: 'monitor', label: '用户监控', en: 'monitor_enabled' },
  { key: 'sum', label: 'AI总结' },
  { key: 'explain', label: '解释命令', en: 'enable_explain_command' },
  { key: 'scope', label: '范围' },
];

const tab = ref('settings');
const debugLogs = ref([]);
const group = ref('api');
const loading = ref(true);
const saving = ref(false);
const testing = ref(false);
const autoSaying = ref(false);
const cfg = reactive({ ...DEFAULTS });

// 对话记忆
const histories = ref([]);
const proactiveNext = ref('');
const histLoading = ref(false);
const activeChat = ref(null);
const chatMessages = ref([]);
const msgLoading = ref(false);

onMounted(async () => {
  try {
    const saved = await props.host.getConfig();
    Object.assign(cfg, DEFAULTS, saved || {});
    parseMonitors();
    const d = await props.host.callApi('/get_debug_logs', 'GET');
    if (d?.logs) debugLogs.value = d.logs;
  } catch (e) {
    props.host.toast.error('读取配置失败：' + (e.message || e));
  } finally {
    loading.value = false;
  }
});

// ── 用户监控 ──
const parsedMonitors = ref([]);

function syncMonitors() {
  cfg.monitor_config = JSON.stringify(parsedMonitors.value, null, 2);
}

function parseMonitors() {
  try {
    const raw = JSON.parse(cfg.monitor_config || '[]');
    parsedMonitors.value = raw.map(r => ({
      ...r,
      triggers: r.triggers || []
    }));
  } catch {
    parsedMonitors.value = [];
  }
}

function addMonitor() {
  parsedMonitors.value.push({ user_ids: '', chat_ids: '', first_reply: '', triggers: [] });
  syncMonitors();
}

function delMonitor(ri) {
  parsedMonitors.value.splice(ri, 1);
  syncMonitors();
}

function addTrigger(ri) {
  parsedMonitors.value[ri].triggers.push({ keyword: '', reply: '' });
  syncMonitors();
}

function delTrigger(ri, ti) {
  parsedMonitors.value[ri].triggers.splice(ti, 1);
  syncMonitors();
}

async function resetMonitor(ri) {
  const rule = parsedMonitors.value[ri];
  const users = (rule.user_ids || '').split(',').map(s => s.trim()).filter(Boolean);
  const chats = (rule.chat_ids || '').split(',').map(s => s.trim()).filter(Boolean);
  if (!users.length || !chats.length) {
    props.host.toast.error('请先填用户ID和群组ID');
    return
  }
  for (const uid of users) {
    for (const cid of chats) {
      await props.host.callApi('/reset_monitor', 'POST', { user_id: uid, chat_id: cid });
    }
  }
  props.host.toast.success('已重置');
}

// Watch for changes in parsedMonitors to sync back
watch(parsedMonitors, syncMonitors, { deep: true });

async function save() {
  syncMonitors();
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

async function testConn() {
  testing.value = true;
  try {
    const r = await props.host.callApi('/test', { method: 'POST', body: {} });
    if (r.ok) props.host.toast.success('连接正常 ✅ ' + (r.model || ''));
    else props.host.toast.error('连接失败：' + (r.message || '未知'));
  } catch (e) {
    props.host.toast.error('连接失败：' + (e.message || e));
  } finally {
    testing.value = false;
  }
}

async function testAutoSay() {
  autoSaying.value = true;
  try {
    const r = await props.host.callApi('/auto_say_test', { method: 'POST', body: {} });
    if (r.ok) props.host.toast.success('✅ 已触发自动发言，群内查看效果');
    else props.host.toast.error('触发失败：' + (r.message || '未知'));
  } catch (e) {
    props.host.toast.error('触发失败：' + (e.message || e));
  } finally {
    autoSaying.value = false;
  }
}

// ── 对话记忆 ──
async function loadHistories() {
  histLoading.value = true;
  try {
    const r = await props.host.callApi('/histories');
    histories.value = r.items || [];
    proactiveNext.value = r.proactive_next || '';
  } catch (e) {
    props.host.toast.error('读取会话列表失败：' + (e.message || e));
  } finally {
    histLoading.value = false;
  }
}
async function openChat(h) {
  activeChat.value = h;
  msgLoading.value = true;
  chatMessages.value = [];
  try {
    const r = await props.host.callApi('/history?chat_id=' + encodeURIComponent(h.chat_id));
    chatMessages.value = r.messages || [];
  } catch (e) {
    props.host.toast.error('读取会话历史失败：' + (e.message || e));
  } finally {
    msgLoading.value = false;
  }
}
async function clearChat(h) {
  if (!confirm(`清空会话 ${h.chat_id} 的对话记忆？`)) return
  try {
    await props.host.callApi('/history/clear', { method: 'POST', body: { chat_id: h.chat_id } });
    histories.value = histories.value.filter(x => x.chat_id !== h.chat_id);
    if (activeChat.value && activeChat.value.chat_id === h.chat_id) {
      activeChat.value = null;
      chatMessages.value = [];
    }
    props.host.toast.success('已清空');
  } catch (e) { props.host.toast.error('清空失败：' + (e.message || e)); }
}
async function clearAll() {
  if (!confirm('清空全部会话的对话记忆？')) return
  try {
    await props.host.callApi('/history/clear', { method: 'POST', body: { all: true } });
    histories.value = [];
    activeChat.value = null;
    chatMessages.value = [];
    props.host.toast.success('已清空全部');
  } catch (e) { props.host.toast.error('清空失败：' + (e.message || e)); }
}

function switchTab(t) {
  tab.value = t;
  if (t === 'memory' && !histories.value.length) loadHistories();
}

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (loading.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_2, "加载配置…"))
      : (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
          _createElementVNode("div", _hoisted_3, [
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'settings' }]),
              onClick: _cache[0] || (_cache[0] = $event => (switchTab('settings')))
            }, "⚙ 配置", 2),
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'memory' }]),
              onClick: _cache[1] || (_cache[1] = $event => (switchTab('memory')))
            }, "💬 对话记忆", 2),
            _createElementVNode("button", {
              class: _normalizeClass(['tab', { on: tab.value === 'debug' }]),
              onClick: _cache[2] || (_cache[2] = $event => (tab.value='debug'))
            }, "🔍 日志", 2)
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_4, [
            _createElementVNode("aside", _hoisted_5, [
              _cache[32] || (_cache[32] = _createElementVNode("div", { class: "side-title" }, "设置分组", -1)),
              (_openBlock(), _createElementBlock(_Fragment, null, _renderList(GROUPS, (g) => {
                return _createElementVNode("button", {
                  key: g.key,
                  class: _normalizeClass(['side-item', { on: group.value === g.key }]),
                  onClick: $event => (group.value = g.key)
                }, [
                  _createElementVNode("span", null, _toDisplayString(g.label), 1),
                  (g.en && cfg[g.en])
                    ? (_openBlock(), _createElementBlock("span", _hoisted_7))
                    : _createCommentVNode("", true)
                ], 10, _hoisted_6)
              }), 64))
            ]),
            _createElementVNode("div", _hoisted_8, [
              (group.value === 'api')
                ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                    _cache[36] || (_cache[36] = _createElementVNode("h3", { class: "det-title" }, "OpenAI 兼容接口", -1)),
                    _createElementVNode("section", _hoisted_9, [
                      _createElementVNode("label", _hoisted_10, [
                        _cache[33] || (_cache[33] = _createElementVNode("span", null, "API Key", -1)),
                        _withDirectives(_createElementVNode("input", {
                          "onUpdate:modelValue": _cache[3] || (_cache[3] = $event => ((cfg.api_key) = $event)),
                          class: "inp",
                          type: "password",
                          placeholder: "接口密钥"
                        }, null, 512), [
                          [_vModelText, cfg.api_key]
                        ])
                      ]),
                      _createElementVNode("label", _hoisted_11, [
                        _cache[34] || (_cache[34] = _createElementVNode("span", null, "接口地址", -1)),
                        _withDirectives(_createElementVNode("input", {
                          "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((cfg.base_url) = $event)),
                          class: "inp",
                          placeholder: "https://api.openai.com/v1（留空用官方默认）"
                        }, null, 512), [
                          [_vModelText, cfg.base_url]
                        ])
                      ]),
                      _createElementVNode("label", _hoisted_12, [
                        _cache[35] || (_cache[35] = _createElementVNode("span", null, "模型", -1)),
                        _withDirectives(_createElementVNode("input", {
                          "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((cfg.model) = $event)),
                          class: "inp",
                          placeholder: "gpt-4o-mini / gpt-3.5-turbo 等"
                        }, null, 512), [
                          [_vModelText, cfg.model]
                        ])
                      ]),
                      _createElementVNode("div", _hoisted_13, [
                        _createElementVNode("button", {
                          class: "btn",
                          disabled: testing.value,
                          onClick: testConn
                        }, _toDisplayString(testing.value ? '测试中…' : '测试连接'), 9, _hoisted_14)
                      ])
                    ])
                  ], 64))
                : (group.value === 'human')
                  ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                      _cache[45] || (_cache[45] = _createElementVNode("h3", { class: "det-title" }, "人形回复", -1)),
                      _createElementVNode("section", _hoisted_15, [
                        _createElementVNode("label", _hoisted_16, [
                          _withDirectives(_createElementVNode("input", {
                            "onUpdate:modelValue": _cache[6] || (_cache[6] = $event => ((cfg.enable_private_chat) = $event)),
                            type: "checkbox"
                          }, null, 512), [
                            [_vModelCheckbox, cfg.enable_private_chat]
                          ]),
                          _cache[37] || (_cache[37] = _createElementVNode("span", null, "私聊回复（私聊里直接对话）", -1))
                        ]),
                        _createElementVNode("label", _hoisted_17, [
                          _withDirectives(_createElementVNode("input", {
                            "onUpdate:modelValue": _cache[7] || (_cache[7] = $event => ((cfg.enable_group_chat) = $event)),
                            type: "checkbox"
                          }, null, 512), [
                            [_vModelCheckbox, cfg.enable_group_chat]
                          ]),
                          _cache[38] || (_cache[38] = _createElementVNode("span", null, "群聊回复（群里 @你 或回复你的消息时对话）", -1))
                        ]),
                        (cfg.enable_group_chat)
                          ? (_openBlock(), _createElementBlock("label", _hoisted_18, [
                              _cache[39] || (_cache[39] = _createElementVNode("span", null, "生效群组", -1)),
                              _withDirectives(_createElementVNode("textarea", {
                                "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((cfg.group_chat_ids) = $event)),
                                class: "inp",
                                rows: "2",
                                placeholder: "群ID逗号分隔，留空=所有群"
                              }, null, 512), [
                                [_vModelText, cfg.group_chat_ids]
                              ])
                            ]))
                          : _createCommentVNode("", true),
                        _createElementVNode("label", _hoisted_19, [
                          _cache[40] || (_cache[40] = _createElementVNode("span", null, "人设", -1)),
                          _withDirectives(_createElementVNode("textarea", {
                            "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((cfg.system_prompt) = $event)),
                            class: "inp",
                            rows: "8",
                            placeholder: "系统提示词"
                          }, null, 512), [
                            [_vModelText, cfg.system_prompt]
                          ])
                        ]),
                        _createElementVNode("label", _hoisted_20, [
                          _cache[41] || (_cache[41] = _createElementVNode("span", null, "记忆轮数", -1)),
                          _withDirectives(_createElementVNode("input", {
                            "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((cfg.max_history) = $event)),
                            class: "inp sm",
                            type: "number",
                            min: "0",
                            max: "40"
                          }, null, 512), [
                            [
                              _vModelText,
                              cfg.max_history,
                              void 0,
                              { number: true }
                            ]
                          ]),
                          _cache[42] || (_cache[42] = _createElementVNode("span", { class: "hint" }, "每会话保留多少条历史，0=不记忆", -1))
                        ]),
                        _createElementVNode("label", _hoisted_21, [
                          _cache[43] || (_cache[43] = _createElementVNode("span", null, "跟随窗口", -1)),
                          _withDirectives(_createElementVNode("input", {
                            "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((cfg.follow_minutes) = $event)),
                            class: "inp sm",
                            type: "number",
                            min: "0",
                            max: "60"
                          }, null, 512), [
                            [
                              _vModelText,
                              cfg.follow_minutes,
                              void 0,
                              { number: true }
                            ]
                          ]),
                          _cache[44] || (_cache[44] = _createElementVNode("span", { class: "hint" }, "@/回复后几分钟内跟随聊天，0=关闭", -1))
                        ])
                      ])
                    ], 64))
                  : (group.value === 'proactive')
                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                        _cache[53] || (_cache[53] = _createElementVNode("h3", { class: "det-title" }, "随机主动搭话", -1)),
                        _createElementVNode("section", _hoisted_22, [
                          _createElementVNode("label", _hoisted_23, [
                            _withDirectives(_createElementVNode("input", {
                              "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((cfg.enable_proactive) = $event)),
                              type: "checkbox"
                            }, null, 512), [
                              [_vModelCheckbox, cfg.enable_proactive]
                            ]),
                            _cache[46] || (_cache[46] = _createElementVNode("span", null, "开启随机主动搭话", -1))
                          ]),
                          _cache[52] || (_cache[52] = _createElementVNode("p", { class: "tip" }, "在下方群组里每隔随机时间挑一条群友近期消息主动接话开启话题；群友回复你后走人形对话续聊（需「群聊回复」开着）。", -1)),
                          (cfg.enable_proactive)
                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                _createElementVNode("label", _hoisted_24, [
                                  _cache[47] || (_cache[47] = _createElementVNode("span", null, "搭话群组", -1)),
                                  _withDirectives(_createElementVNode("textarea", {
                                    "onUpdate:modelValue": _cache[13] || (_cache[13] = $event => ((cfg.proactive_chat_ids) = $event)),
                                    class: "inp",
                                    rows: "2",
                                    placeholder: "群ID逗号分隔，必填"
                                  }, null, 512), [
                                    [_vModelText, cfg.proactive_chat_ids]
                                  ])
                                ]),
                                _createElementVNode("div", _hoisted_25, [
                                  _createElementVNode("label", _hoisted_26, [
                                    _cache[48] || (_cache[48] = _createElementVNode("span", null, "间隔最小", -1)),
                                    _withDirectives(_createElementVNode("input", {
                                      "onUpdate:modelValue": _cache[14] || (_cache[14] = $event => ((cfg.proactive_min_minutes) = $event)),
                                      class: "inp sm",
                                      type: "number",
                                      min: "5",
                                      max: "720"
                                    }, null, 512), [
                                      [
                                        _vModelText,
                                        cfg.proactive_min_minutes,
                                        void 0,
                                        { number: true }
                                      ]
                                    ]),
                                    _cache[49] || (_cache[49] = _createElementVNode("span", { class: "hint" }, "分钟", -1))
                                  ]),
                                  _createElementVNode("label", _hoisted_27, [
                                    _cache[50] || (_cache[50] = _createElementVNode("span", null, "间隔最大", -1)),
                                    _withDirectives(_createElementVNode("input", {
                                      "onUpdate:modelValue": _cache[15] || (_cache[15] = $event => ((cfg.proactive_max_minutes) = $event)),
                                      class: "inp sm",
                                      type: "number",
                                      min: "5",
                                      max: "1440"
                                    }, null, 512), [
                                      [
                                        _vModelText,
                                        cfg.proactive_max_minutes,
                                        void 0,
                                        { number: true }
                                      ]
                                    ]),
                                    _cache[51] || (_cache[51] = _createElementVNode("span", { class: "hint" }, "分钟", -1))
                                  ])
                                ])
                              ], 64))
                            : _createCommentVNode("", true)
                        ])
                      ], 64))
                    : (group.value === 'autosay')
                      ? (_openBlock(), _createElementBlock(_Fragment, { key: 3 }, [
                          _cache[67] || (_cache[67] = _createElementVNode("h3", { class: "det-title" }, "自动发言", -1)),
                          _createElementVNode("section", _hoisted_28, [
                            _createElementVNode("label", _hoisted_29, [
                              _withDirectives(_createElementVNode("input", {
                                "onUpdate:modelValue": _cache[16] || (_cache[16] = $event => ((cfg.enable_auto_say) = $event)),
                                type: "checkbox"
                              }, null, 512), [
                                [_vModelCheckbox, cfg.enable_auto_say]
                              ]),
                              _cache[54] || (_cache[54] = _createElementVNode("span", null, "开启定时自动发言", -1))
                            ]),
                            _createElementVNode("label", _hoisted_30, [
                              _withDirectives(_createElementVNode("input", {
                                "onUpdate:modelValue": _cache[17] || (_cache[17] = $event => ((cfg.enable_reward_answer) = $event)),
                                type: "checkbox"
                              }, null, 512), [
                                [_vModelCheckbox, cfg.enable_reward_answer]
                              ]),
                              _cache[55] || (_cache[55] = _createElementVNode("span", null, "答题奖励（自动回复机器人数学题）", -1))
                            ]),
                            (cfg.enable_reward_answer)
                              ? (_openBlock(), _createElementBlock("label", _hoisted_31, [
                                  _cache[56] || (_cache[56] = _createElementVNode("span", null, "指定机器人", -1)),
                                  _withDirectives(_createElementVNode("input", {
                                    "onUpdate:modelValue": _cache[18] || (_cache[18] = $event => ((cfg.reward_bot_ids) = $event)),
                                    class: "inp",
                                    placeholder: "机器人ID或用户名，逗号分隔，留空则回复所有"
                                  }, null, 512), [
                                    [_vModelText, cfg.reward_bot_ids]
                                  ])
                                ]))
                              : _createCommentVNode("", true),
                            _cache[66] || (_cache[66] = _createElementVNode("p", { class: "tip" }, "在下方群组里每隔随机时间随机选 2 条发言，间隔 15-20 秒。至少需要 2 条可选。", -1)),
                            (cfg.enable_auto_say)
                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 1 }, [
                                  _createElementVNode("label", _hoisted_32, [
                                    _cache[57] || (_cache[57] = _createElementVNode("span", null, "发言群组", -1)),
                                    _withDirectives(_createElementVNode("textarea", {
                                      "onUpdate:modelValue": _cache[19] || (_cache[19] = $event => ((cfg.auto_say_chat_ids) = $event)),
                                      class: "inp",
                                      rows: "2",
                                      placeholder: "群ID逗号分隔，必填"
                                    }, null, 512), [
                                      [_vModelText, cfg.auto_say_chat_ids]
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_33, [
                                    _createElementVNode("label", _hoisted_34, [
                                      _cache[58] || (_cache[58] = _createElementVNode("span", null, "间隔最小", -1)),
                                      _withDirectives(_createElementVNode("input", {
                                        "onUpdate:modelValue": _cache[20] || (_cache[20] = $event => ((cfg.auto_say_min_minutes) = $event)),
                                        class: "inp sm",
                                        type: "number",
                                        min: "1",
                                        max: "120"
                                      }, null, 512), [
                                        [
                                          _vModelText,
                                          cfg.auto_say_min_minutes,
                                          void 0,
                                          { number: true }
                                        ]
                                      ]),
                                      _cache[59] || (_cache[59] = _createElementVNode("span", { class: "hint" }, "分钟", -1))
                                    ]),
                                    _createElementVNode("label", _hoisted_35, [
                                      _cache[60] || (_cache[60] = _createElementVNode("span", null, "间隔最大", -1)),
                                      _withDirectives(_createElementVNode("input", {
                                        "onUpdate:modelValue": _cache[21] || (_cache[21] = $event => ((cfg.auto_say_max_minutes) = $event)),
                                        class: "inp sm",
                                        type: "number",
                                        min: "1",
                                        max: "240"
                                      }, null, 512), [
                                        [
                                          _vModelText,
                                          cfg.auto_say_max_minutes,
                                          void 0,
                                          { number: true }
                                        ]
                                      ]),
                                      _cache[61] || (_cache[61] = _createElementVNode("span", { class: "hint" }, "分钟", -1))
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_36, [
                                    _createElementVNode("label", _hoisted_37, [
                                      _cache[62] || (_cache[62] = _createElementVNode("span", null, "开始时间", -1)),
                                      _withDirectives(_createElementVNode("input", {
                                        "onUpdate:modelValue": _cache[22] || (_cache[22] = $event => ((cfg.auto_say_time_start) = $event)),
                                        class: "inp sm",
                                        placeholder: "09:00"
                                      }, null, 512), [
                                        [_vModelText, cfg.auto_say_time_start]
                                      ])
                                    ]),
                                    _createElementVNode("label", _hoisted_38, [
                                      _cache[63] || (_cache[63] = _createElementVNode("span", null, "结束时间", -1)),
                                      _withDirectives(_createElementVNode("input", {
                                        "onUpdate:modelValue": _cache[23] || (_cache[23] = $event => ((cfg.auto_say_time_end) = $event)),
                                        class: "inp sm",
                                        placeholder: "23:00"
                                      }, null, 512), [
                                        [_vModelText, cfg.auto_say_time_end]
                                      ])
                                    ])
                                  ]),
                                  _createElementVNode("label", _hoisted_39, [
                                    _withDirectives(_createElementVNode("input", {
                                      "onUpdate:modelValue": _cache[24] || (_cache[24] = $event => ((cfg.auto_say_use_lyrics) = $event)),
                                      type: "checkbox"
                                    }, null, 512), [
                                      [_vModelCheckbox, cfg.auto_say_use_lyrics]
                                    ]),
                                    _cache[64] || (_cache[64] = _createElementVNode("span", null, "混入随机歌词（内置 300+ 条经典歌词）", -1))
                                  ]),
                                  _createElementVNode("label", _hoisted_40, [
                                    _cache[65] || (_cache[65] = _createElementVNode("span", null, "发言词条", -1)),
                                    _withDirectives(_createElementVNode("textarea", {
                                      "onUpdate:modelValue": _cache[25] || (_cache[25] = $event => ((cfg.auto_say_phrases) = $event)),
                                      class: "inp",
                                      rows: "8",
                                      placeholder: "每行一条，随机选 2 条发送\n例如：\n有人吗😂\n今天好安静啊\n摸鱼中…\n吃饭了没\n好无聊谁来聊两句"
                                    }, null, 512), [
                                      [_vModelText, cfg.auto_say_phrases]
                                    ])
                                  ]),
                                  _createElementVNode("div", _hoisted_41, [
                                    _createElementVNode("button", {
                                      class: "btn",
                                      disabled: autoSaying.value,
                                      onClick: testAutoSay
                                    }, _toDisplayString(autoSaying.value ? '发言中…' : '🔘 测试发言'), 9, _hoisted_42)
                                  ])
                                ], 64))
                              : _createCommentVNode("", true)
                          ])
                        ], 64))
                      : (group.value === 'sum')
                        ? (_openBlock(), _createElementBlock(_Fragment, { key: 4 }, [
                            _cache[68] || (_cache[68] = _createStaticVNode("<h3 class=\"det-title\" data-v-4a18e79c>群消息总结（.sum 命令）</h3><section class=\"card\" data-v-4a18e79c><p class=\"tip\" data-v-4a18e79c>在群聊中发送 <code data-v-4a18e79c>.sum 100</code> 快速总结最近消息，无需额外配置，复用 AI 接口配置。</p><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum 100</code> — 总结最近100条 </div><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum add 群组ID 2h 100</code> — 添加定时总结任务 </div><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum list</code> — 查看所有任务 </div><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum run 1</code> — 立即执行任务 </div><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum del 1</code> — 删除任务 </div><div class=\"row-usage\" data-v-4a18e79c><code data-v-4a18e79c>.sum disable 1</code> — 禁用任务 </div><p class=\"tip\" style=\"margin-top:8px;\" data-v-4a18e79c>间隔格式: <code data-v-4a18e79c>2h</code>(2小时), <code data-v-4a18e79c>30m</code>(30分钟), 或 cron 表达式</p></section>", 2))
                          ], 64))
                        : (group.value === 'explain')
                          ? (_openBlock(), _createElementBlock(_Fragment, { key: 5 }, [
                              _cache[73] || (_cache[73] = _createElementVNode("h3", { class: "det-title" }, "/ai 解释命令", -1)),
                              _createElementVNode("section", _hoisted_43, [
                                _createElementVNode("label", _hoisted_44, [
                                  _withDirectives(_createElementVNode("input", {
                                    "onUpdate:modelValue": _cache[26] || (_cache[26] = $event => ((cfg.enable_explain_command) = $event)),
                                    type: "checkbox"
                                  }, null, 512), [
                                    [_vModelCheckbox, cfg.enable_explain_command]
                                  ]),
                                  _cache[69] || (_cache[69] = _createElementVNode("span", null, "启用 /ai 解释命令", -1))
                                ]),
                                _cache[72] || (_cache[72] = _createElementVNode("p", { class: "tip" }, "回复一条消息（或图片）再发 /ai，让 AI 解释/解答（单次，无记忆）。", -1)),
                                (cfg.enable_explain_command)
                                  ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                      _createElementVNode("label", _hoisted_45, [
                                        _withDirectives(_createElementVNode("input", {
                                          "onUpdate:modelValue": _cache[27] || (_cache[27] = $event => ((cfg.enable_explain_prompt) = $event)),
                                          type: "checkbox"
                                        }, null, 512), [
                                          [_vModelCheckbox, cfg.enable_explain_prompt]
                                        ]),
                                        _cache[70] || (_cache[70] = _createElementVNode("span", null, "用解释模板（否则直接把内容丢给 AI）", -1))
                                      ]),
                                      (cfg.enable_explain_prompt)
                                        ? (_openBlock(), _createElementBlock("label", _hoisted_46, [
                                            _cache[71] || (_cache[71] = _createElementVNode("span", null, "解释模板", -1)),
                                            _withDirectives(_createElementVNode("textarea", {
                                              "onUpdate:modelValue": _cache[28] || (_cache[28] = $event => ((cfg.explain_prompt) = $event)),
                                              class: "inp",
                                              rows: "6",
                                              placeholder: "用 {content} 占位被解释的内容"
                                            }, null, 512), [
                                              [_vModelText, cfg.explain_prompt]
                                            ])
                                          ]))
                                        : _createCommentVNode("", true)
                                    ], 64))
                                  : _createCommentVNode("", true)
                              ])
                            ], 64))
                          : (group.value === 'monitor')
                            ? (_openBlock(), _createElementBlock(_Fragment, { key: 6 }, [
                                _cache[82] || (_cache[82] = _createElementVNode("h3", { class: "det-title" }, "用户监控", -1)),
                                _createElementVNode("section", _hoisted_47, [
                                  _createElementVNode("label", _hoisted_48, [
                                    _withDirectives(_createElementVNode("input", {
                                      "onUpdate:modelValue": _cache[29] || (_cache[29] = $event => ((cfg.monitor_enabled) = $event)),
                                      type: "checkbox"
                                    }, null, 512), [
                                      [_vModelCheckbox, cfg.monitor_enabled]
                                    ]),
                                    _cache[74] || (_cache[74] = _createElementVNode("span", null, "开启用户监控", -1))
                                  ]),
                                  (cfg.monitor_enabled)
                                    ? (_openBlock(), _createElementBlock(_Fragment, { key: 0 }, [
                                        (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(parsedMonitors.value, (rule, ri) => {
                                          return (_openBlock(), _createElementBlock("div", {
                                            key: ri,
                                            class: "mon-card"
                                          }, [
                                            _createElementVNode("div", _hoisted_49, [
                                              _createElementVNode("b", null, "规则 #" + _toDisplayString(ri + 1), 1),
                                              _createElementVNode("div", _hoisted_50, [
                                                _createElementVNode("button", {
                                                  class: "btn sm",
                                                  onClick: $event => (resetMonitor(ri))
                                                }, "重置", 8, _hoisted_51),
                                                _createElementVNode("button", {
                                                  class: "btn sm danger",
                                                  onClick: $event => (delMonitor(ri))
                                                }, "删除", 8, _hoisted_52)
                                              ])
                                            ]),
                                            _createElementVNode("label", _hoisted_53, [
                                              _cache[75] || (_cache[75] = _createElementVNode("span", null, "用户ID", -1)),
                                              _withDirectives(_createElementVNode("input", {
                                                "onUpdate:modelValue": $event => ((rule.user_ids) = $event),
                                                class: "inp",
                                                placeholder: "逗号分隔"
                                              }, null, 8, _hoisted_54), [
                                                [_vModelText, rule.user_ids]
                                              ])
                                            ]),
                                            _createElementVNode("label", _hoisted_55, [
                                              _cache[76] || (_cache[76] = _createElementVNode("span", null, "群组ID", -1)),
                                              _withDirectives(_createElementVNode("input", {
                                                "onUpdate:modelValue": $event => ((rule.chat_ids) = $event),
                                                class: "inp",
                                                placeholder: "逗号分隔"
                                              }, null, 8, _hoisted_56), [
                                                [_vModelText, rule.chat_ids]
                                              ])
                                            ]),
                                            _createElementVNode("label", _hoisted_57, [
                                              _cache[77] || (_cache[77] = _createElementVNode("span", null, "首句回复", -1)),
                                              _withDirectives(_createElementVNode("input", {
                                                "onUpdate:modelValue": $event => ((rule.first_reply) = $event),
                                                class: "inp",
                                                placeholder: "必填，对方第一句自动回复"
                                              }, null, 8, _hoisted_58), [
                                                [_vModelText, rule.first_reply]
                                              ])
                                            ]),
                                            _createElementVNode("label", _hoisted_59, [
                                              _cache[78] || (_cache[78] = _createElementVNode("span", null, "重置周期", -1)),
                                              _withDirectives(_createElementVNode("input", {
                                                "onUpdate:modelValue": $event => ((rule.reset_hours) = $event),
                                                class: "inp sm",
                                                type: "number",
                                                min: "0",
                                                placeholder: "0"
                                              }, null, 8, _hoisted_60), [
                                                [
                                                  _vModelText,
                                                  rule.reset_hours,
                                                  void 0,
                                                  { number: true }
                                                ]
                                              ]),
                                              _cache[79] || (_cache[79] = _createElementVNode("span", { class: "hint" }, "小时，0=不重置", -1))
                                            ]),
                                            _cache[81] || (_cache[81] = _createElementVNode("div", { class: "trig-title" }, "关键词触发回复：", -1)),
                                            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rule.triggers, (tr, ti) => {
                                              return (_openBlock(), _createElementBlock("div", {
                                                key: ti,
                                                class: "trig-row"
                                              }, [
                                                _withDirectives(_createElementVNode("input", {
                                                  "onUpdate:modelValue": $event => ((tr.keywords) = $event),
                                                  class: "inp",
                                                  placeholder: "关键词,逗号分隔",
                                                  style: {"width":"160px"}
                                                }, null, 8, _hoisted_61), [
                                                  [_vModelText, tr.keywords]
                                                ]),
                                                _cache[80] || (_cache[80] = _createElementVNode("span", { class: "arr" }, "→", -1)),
                                                _withDirectives(_createElementVNode("input", {
                                                  "onUpdate:modelValue": $event => ((tr.replies) = $event),
                                                  class: "inp",
                                                  placeholder: "回复内容,逗号分隔多条随机选"
                                                }, null, 8, _hoisted_62), [
                                                  [_vModelText, tr.replies]
                                                ]),
                                                _createElementVNode("button", {
                                                  class: "btn sm danger",
                                                  onClick: $event => (delTrigger(ri, ti))
                                                }, "✕", 8, _hoisted_63)
                                              ]))
                                            }), 128)),
                                            _createElementVNode("button", {
                                              class: "btn sm",
                                              onClick: $event => (addTrigger(ri))
                                            }, "＋ 添加关键词", 8, _hoisted_64)
                                          ]))
                                        }), 128)),
                                        _createElementVNode("button", {
                                          class: "btn",
                                          style: {"width":"100%","margin-top":"8px"},
                                          onClick: addMonitor
                                        }, "＋ 添加规则")
                                      ], 64))
                                    : _createCommentVNode("", true)
                                ])
                              ], 64))
                            : (group.value === 'scope')
                              ? (_openBlock(), _createElementBlock(_Fragment, { key: 7 }, [
                                  _cache[85] || (_cache[85] = _createElementVNode("h3", { class: "det-title" }, "生效范围", -1)),
                                  _createElementVNode("section", _hoisted_65, [
                                    _createElementVNode("label", _hoisted_66, [
                                      _cache[83] || (_cache[83] = _createElementVNode("span", null, "会话白名单", -1)),
                                      _withDirectives(_createElementVNode("textarea", {
                                        "onUpdate:modelValue": _cache[30] || (_cache[30] = $event => ((cfg.white_list_chats) = $event)),
                                        class: "inp",
                                        rows: "2",
                                        placeholder: "会话ID逗号分隔，留空=所有会话"
                                      }, null, 512), [
                                        [_vModelText, cfg.white_list_chats]
                                      ])
                                    ]),
                                    _createElementVNode("label", _hoisted_67, [
                                      _cache[84] || (_cache[84] = _createElementVNode("span", null, "群组黑名单", -1)),
                                      _withDirectives(_createElementVNode("textarea", {
                                        "onUpdate:modelValue": _cache[31] || (_cache[31] = $event => ((cfg.blacklist_chats) = $event)),
                                        class: "inp",
                                        rows: "2",
                                        placeholder: "群ID逗号分隔，在这些群中完全不生效"
                                      }, null, 512), [
                                        [_vModelText, cfg.blacklist_chats]
                                      ])
                                    ])
                                  ])
                                ], 64))
                              : _createCommentVNode("", true),
              _createElementVNode("div", _hoisted_68, [
                _createElementVNode("button", {
                  class: "btn primary lg",
                  disabled: saving.value,
                  onClick: save
                }, _toDisplayString(saving.value ? '保存中…' : '保存配置'), 9, _hoisted_69)
              ])
            ])
          ], 512), [
            [_vShow, tab.value === 'settings']
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_70, [
            _createElementVNode("div", _hoisted_71, [
              _createElementVNode("span", _hoisted_72, "下次主动搭话：" + _toDisplayString(proactiveNext.value || '—'), 1),
              _cache[86] || (_cache[86] = _createElementVNode("span", { class: "grow" }, null, -1)),
              _createElementVNode("button", {
                class: "btn",
                onClick: loadHistories
              }, "刷新"),
              _createElementVNode("button", {
                class: "btn danger",
                disabled: !histories.value.length,
                onClick: clearAll
              }, "全部清空", 8, _hoisted_73)
            ]),
            (histLoading.value)
              ? (_openBlock(), _createElementBlock("div", _hoisted_74, "加载中…"))
              : (!histories.value.length)
                ? (_openBlock(), _createElementBlock("div", _hoisted_75, [...(_cache[87] || (_cache[87] = [
                    _createTextVNode("暂无对话记忆", -1),
                    _createElementVNode("br", null, null, -1),
                    _createElementVNode("span", { class: "muted" }, "私聊/群@你对话后会在这里记录会话记忆", -1)
                  ]))]))
                : (_openBlock(), _createElementBlock("div", _hoisted_76, [
                    _createElementVNode("div", _hoisted_77, [
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(histories.value, (h) => {
                        return (_openBlock(), _createElementBlock("button", {
                          key: h.chat_id,
                          class: _normalizeClass(['mem-item', { on: activeChat.value && activeChat.value.chat_id === h.chat_id }]),
                          onClick: $event => (openChat(h))
                        }, [
                          _createElementVNode("div", _hoisted_79, [
                            _createElementVNode("span", _hoisted_80, _toDisplayString(h.is_private ? '私聊' : '群'), 1),
                            _createElementVNode("span", _hoisted_81, _toDisplayString(h.chat_id), 1)
                          ]),
                          _createElementVNode("div", _hoisted_82, _toDisplayString(h.last || '—'), 1),
                          _createElementVNode("div", _hoisted_83, [
                            _createTextVNode(_toDisplayString(h.count) + " 条 · ", 1),
                            _createElementVNode("a", {
                              class: "lnk",
                              onClick: _withModifiers($event => (clearChat(h)), ["stop"])
                            }, "清空", 8, _hoisted_84)
                          ])
                        ], 10, _hoisted_78))
                      }), 128))
                    ]),
                    _createElementVNode("div", _hoisted_85, [
                      (!activeChat.value)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_86, "← 选择一个会话查看历史"))
                        : (msgLoading.value)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_87, "加载中…"))
                          : (_openBlock(), _createElementBlock("div", _hoisted_88, [
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(chatMessages.value, (m, i) => {
                                return (_openBlock(), _createElementBlock("div", {
                                  key: i,
                                  class: _normalizeClass(['bubble', m.role])
                                }, [
                                  _createElementVNode("div", _hoisted_89, _toDisplayString(m.role === 'user' ? '对方' : '我'), 1),
                                  _createElementVNode("div", _hoisted_90, _toDisplayString(m.content), 1)
                                ], 2))
                              }), 128))
                            ]))
                    ])
                  ]))
          ], 512), [
            [_vShow, tab.value === 'memory']
          ]),
          _withDirectives(_createElementVNode("div", _hoisted_91, [
            (!debugLogs.value.length)
              ? (_openBlock(), _createElementBlock("div", _hoisted_92, "暂无日志"))
              : _createCommentVNode("", true),
            (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(debugLogs.value, (log) => {
              return (_openBlock(), _createElementBlock("div", {
                key: log.t,
                class: "log-row"
              }, [
                _createElementVNode("span", _hoisted_93, _toDisplayString(log.t), 1),
                _createElementVNode("span", _hoisted_94, _toDisplayString(log.m), 1)
              ]))
            }), 128))
          ], 512), [
            [_vShow, tab.value === 'debug']
          ])
        ], 64))
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-4a18e79c"]]);

export { Config as default };
