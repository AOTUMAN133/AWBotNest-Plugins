import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,vModelCheckbox:_vModelCheckbox,withDirectives:_withDirectives,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,vModelText:_vModelText} = await importShared('vue');


const _hoisted_1 = { class: "monitor-config" };
const _hoisted_2 = { class: "header" };
const _hoisted_3 = { class: "actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = { class: "switches" };
const _hoisted_6 = { class: "switch-row" };
const _hoisted_7 = { class: "switch-row" };
const _hoisted_8 = {
  key: 0,
  class: "loading"
};
const _hoisted_9 = {
  key: 1,
  class: "rules"
};
const _hoisted_10 = { class: "rule-header" };
const _hoisted_11 = { class: "rule-title" };
const _hoisted_12 = ["onClick"];
const _hoisted_13 = { class: "rule-body" };
const _hoisted_14 = { class: "field" };
const _hoisted_15 = ["onUpdate:modelValue"];
const _hoisted_16 = { class: "field" };
const _hoisted_17 = ["onUpdate:modelValue"];
const _hoisted_18 = { class: "field-row" };
const _hoisted_19 = { class: "field flex" };
const _hoisted_20 = ["onUpdate:modelValue"];
const _hoisted_21 = {
  class: "field",
  style: {"width":"120px"}
};
const _hoisted_22 = ["onUpdate:modelValue"];
const _hoisted_23 = { class: "triggers" };
const _hoisted_24 = { class: "triggers-header" };
const _hoisted_25 = ["onClick"];
const _hoisted_26 = ["onUpdate:modelValue"];
const _hoisted_27 = ["onUpdate:modelValue"];
const _hoisted_28 = ["onClick"];

const {ref,reactive,onMounted} = await importShared('vue');



const _sfc_main = {
  __name: 'Config',
  props: {
  pluginId: { type: String, required: true },
  host: { type: Object, required: true },
},
  setup(__props) {

const props = __props;

const rules = ref([]);
const enabled = ref(false);
const useAi = ref(true);
const loading = ref(true);
const saving = ref(false);

// 加载规则
async function loadRules() {
  loading.value = true;
  try {
    const config = await props.host.getConfig();
    enabled.value = config.monitor_enabled === true || config.monitor_enabled === 'true';
    useAi.value = config.use_ai !== false;
    const r = await props.host.callApi('/get_rules', { method: 'GET' });
    if (r?.ok && r?.rules) {
      rules.value = r.rules.map(normalizeRule);
    } else {
      try {
        const raw = JSON.parse(config.monitor_config || '[]');
        rules.value = Array.isArray(raw) ? raw.map(normalizeRule) : [];
      } catch { rules.value = []; }
    }
  } catch { rules.value = []; }
  if (rules.value.length === 0) rules.value.push(newRule());
  loading.value = false;
}

function normalizeRule(r) {
  return {
    chat_ids: r.chat_ids || '',
    user_ids: r.user_ids || '',
    first_reply: r.first_reply || '',
    reset_hours: r.reset_hours ?? 0,
    triggers: (r.triggers || []).map(t => ({
      keywords: t.keywords || t.keyword || '',
      replies: t.replies || t.reply || '',
    })),
  }
}

function newRule() {
  return { chat_ids: '', user_ids: '', first_reply: '', reset_hours: 0, triggers: [] }
}

function newTrigger() {
  return { keywords: '', replies: '' }
}

function addRule() { rules.value.push(newRule()); }
function delRule(i) { rules.value.splice(i, 1); if (rules.value.length === 0) rules.value.push(newRule()); }
function addTrigger(rule) { rule.triggers.push(newTrigger()); }
function delTrigger(rule, i) { rule.triggers.splice(i, 1); }

async function save() {
  saving.value = true;
  try {
    // 保存开关
    await props.host.saveConfig({ monitor_enabled: enabled.value, use_ai: useAi.value });
    // 保存规则
    const valid = rules.value.filter(r => r.chat_ids.trim() && r.user_ids.trim());
    const r = await props.host.callApi('/save_rules', {
      method: 'POST',
      body: { rules: valid },
    });
    if (r?.ok) {
      props.host.toast.success('已保存');
    } else {
      props.host.toast.error('保存失败: ' + (r?.message || '未知错误'));
    }
  } catch (e) {
    props.host.toast.error('保存失败: ' + (e.message || e));
  }
  saving.value = false;
}

async function resetState() {
  if (!confirm('重置所有监控状态？已触发的关键词将重新开始计数。')) return
  try {
    await props.host.callApi('/reset_monitor', { method: 'POST', body: { all: true } });
    props.host.toast.success('监控状态已重置');
  } catch (e) {
    props.host.toast.error('重置失败: ' + (e.message || e));
  }
}

onMounted(loadRules);

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[2] || (_cache[2] = _createElementVNode("h2", null, "👤 用户监控规则", -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          class: "btn primary",
          onClick: save,
          disabled: saving.value
        }, _toDisplayString(saving.value ? '保存中...' : '💾 保存'), 9, _hoisted_4),
        _createElementVNode("button", {
          class: "btn",
          onClick: addRule
        }, "➕ 添加规则"),
        _createElementVNode("button", {
          class: "btn danger",
          onClick: resetState
        }, "🔄 重置状态")
      ])
    ]),
    _createElementVNode("div", _hoisted_5, [
      _createElementVNode("label", _hoisted_6, [
        _cache[3] || (_cache[3] = _createElementVNode("span", null, "开启监控", -1)),
        _withDirectives(_createElementVNode("input", {
          type: "checkbox",
          "onUpdate:modelValue": _cache[0] || (_cache[0] = $event => ((enabled).value = $event))
        }, null, 512), [
          [_vModelCheckbox, enabled.value]
        ])
      ]),
      _createElementVNode("label", _hoisted_7, [
        _cache[4] || (_cache[4] = _createElementVNode("span", null, "AI智能回复", -1)),
        _withDirectives(_createElementVNode("input", {
          type: "checkbox",
          "onUpdate:modelValue": _cache[1] || (_cache[1] = $event => ((useAi).value = $event))
        }, null, 512), [
          [_vModelCheckbox, useAi.value]
        ])
      ])
    ]),
    (loading.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_8, "加载中..."))
      : (_openBlock(), _createElementBlock("div", _hoisted_9, [
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rules.value, (rule, ri) => {
            return (_openBlock(), _createElementBlock("div", {
              key: ri,
              class: "rule-card"
            }, [
              _createElementVNode("div", _hoisted_10, [
                _createElementVNode("span", _hoisted_11, "规则 #" + _toDisplayString(ri + 1), 1),
                _createElementVNode("button", {
                  class: "btn danger sm",
                  onClick: $event => (delRule(ri))
                }, "🗑 删除", 8, _hoisted_12)
              ]),
              _createElementVNode("div", _hoisted_13, [
                _createElementVNode("div", _hoisted_14, [
                  _cache[5] || (_cache[5] = _createElementVNode("label", null, "群组ID", -1)),
                  _withDirectives(_createElementVNode("input", {
                    "onUpdate:modelValue": $event => ((rule.chat_ids) = $event),
                    class: "inp",
                    placeholder: "多个逗号分隔，如 -1001234567,-1007654321"
                  }, null, 8, _hoisted_15), [
                    [_vModelText, rule.chat_ids]
                  ])
                ]),
                _createElementVNode("div", _hoisted_16, [
                  _cache[6] || (_cache[6] = _createElementVNode("label", null, "用户ID", -1)),
                  _withDirectives(_createElementVNode("input", {
                    "onUpdate:modelValue": $event => ((rule.user_ids) = $event),
                    class: "inp",
                    placeholder: "多个逗号分隔"
                  }, null, 8, _hoisted_17), [
                    [_vModelText, rule.user_ids]
                  ])
                ]),
                _createElementVNode("div", _hoisted_18, [
                  _createElementVNode("div", _hoisted_19, [
                    _cache[7] || (_cache[7] = _createElementVNode("label", null, "首句回复", -1)),
                    _withDirectives(_createElementVNode("input", {
                      "onUpdate:modelValue": $event => ((rule.first_reply) = $event),
                      class: "inp",
                      placeholder: "第一句回复内容"
                    }, null, 8, _hoisted_20), [
                      [_vModelText, rule.first_reply]
                    ])
                  ]),
                  _createElementVNode("div", _hoisted_21, [
                    _cache[8] || (_cache[8] = _createElementVNode("label", null, "重置(小时)", -1)),
                    _withDirectives(_createElementVNode("input", {
                      "onUpdate:modelValue": $event => ((rule.reset_hours) = $event),
                      class: "inp",
                      type: "number",
                      min: "0"
                    }, null, 8, _hoisted_22), [
                      [
                        _vModelText,
                        rule.reset_hours,
                        void 0,
                        { number: true }
                      ]
                    ])
                  ])
                ]),
                _createElementVNode("div", _hoisted_23, [
                  _createElementVNode("div", _hoisted_24, [
                    _cache[9] || (_cache[9] = _createElementVNode("label", null, "关键词触发回复", -1)),
                    _createElementVNode("button", {
                      class: "btn sm",
                      onClick: $event => (addTrigger(rule))
                    }, "➕ 添加", 8, _hoisted_25)
                  ]),
                  (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rule.triggers, (tr, ti) => {
                    return (_openBlock(), _createElementBlock("div", {
                      key: ti,
                      class: "trigger-row"
                    }, [
                      _withDirectives(_createElementVNode("input", {
                        "onUpdate:modelValue": $event => ((tr.keywords) = $event),
                        class: "inp",
                        placeholder: "关键词，逗号分隔"
                      }, null, 8, _hoisted_26), [
                        [_vModelText, tr.keywords]
                      ]),
                      _withDirectives(_createElementVNode("input", {
                        "onUpdate:modelValue": $event => ((tr.replies) = $event),
                        class: "inp",
                        placeholder: "回复内容，逗号分隔"
                      }, null, 8, _hoisted_27), [
                        [_vModelText, tr.replies]
                      ]),
                      _createElementVNode("button", {
                        class: "btn danger sm",
                        onClick: $event => (delTrigger(rule, ti))
                      }, "✕", 8, _hoisted_28)
                    ]))
                  }), 128))
                ])
              ])
            ]))
          }), 128))
        ]))
  ]))
}
}

};
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-ab64ef19"]]);

export { Config as default };
