import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {createElementVNode:_createElementVNode,toDisplayString:_toDisplayString,openBlock:_openBlock,createElementBlock:_createElementBlock,createCommentVNode:_createCommentVNode,renderList:_renderList,Fragment:_Fragment,vModelText:_vModelText,withDirectives:_withDirectives} = await importShared('vue');


const _hoisted_1 = { class: "monitor-config" };
const _hoisted_2 = { class: "header" };
const _hoisted_3 = { class: "actions" };
const _hoisted_4 = ["disabled"];
const _hoisted_5 = {
  key: 0,
  class: "loading"
};
const _hoisted_6 = {
  key: 1,
  class: "rules"
};
const _hoisted_7 = { class: "rule-header" };
const _hoisted_8 = { class: "rule-title" };
const _hoisted_9 = ["onClick"];
const _hoisted_10 = { class: "rule-body" };
const _hoisted_11 = { class: "field" };
const _hoisted_12 = ["onUpdate:modelValue"];
const _hoisted_13 = { class: "field" };
const _hoisted_14 = ["onUpdate:modelValue"];
const _hoisted_15 = { class: "field-row" };
const _hoisted_16 = { class: "field flex" };
const _hoisted_17 = ["onUpdate:modelValue"];
const _hoisted_18 = {
  class: "field",
  style: {"width":"120px"}
};
const _hoisted_19 = ["onUpdate:modelValue"];
const _hoisted_20 = { class: "triggers" };
const _hoisted_21 = { class: "triggers-header" };
const _hoisted_22 = ["onClick"];
const _hoisted_23 = ["onUpdate:modelValue"];
const _hoisted_24 = ["onUpdate:modelValue"];
const _hoisted_25 = ["onClick"];

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
const loading = ref(true);
const saving = ref(false);

// 加载规则
async function loadRules() {
  loading.value = true;
  try {
    const r = await props.host.callApi('/get_rules', { method: 'GET' });
    if (r?.ok && r?.rules) {
      rules.value = r.rules.map(normalizeRule);
    } else {
      const config = await props.host.getConfig();
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
    // 清理空规则
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

onMounted(loadRules);

return (_ctx, _cache) => {
  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    _createElementVNode("div", _hoisted_2, [
      _cache[0] || (_cache[0] = _createElementVNode("h2", null, "👤 用户监控规则", -1)),
      _createElementVNode("div", _hoisted_3, [
        _createElementVNode("button", {
          class: "btn primary",
          onClick: save,
          disabled: saving.value
        }, _toDisplayString(saving.value ? '保存中...' : '💾 保存'), 9, _hoisted_4),
        _createElementVNode("button", {
          class: "btn",
          onClick: addRule
        }, "➕ 添加规则")
      ])
    ]),
    (loading.value)
      ? (_openBlock(), _createElementBlock("div", _hoisted_5, "加载中..."))
      : (_openBlock(), _createElementBlock("div", _hoisted_6, [
          (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(rules.value, (rule, ri) => {
            return (_openBlock(), _createElementBlock("div", {
              key: ri,
              class: "rule-card"
            }, [
              _createElementVNode("div", _hoisted_7, [
                _createElementVNode("span", _hoisted_8, "规则 #" + _toDisplayString(ri + 1), 1),
                _createElementVNode("button", {
                  class: "btn danger sm",
                  onClick: $event => (delRule(ri))
                }, "🗑 删除", 8, _hoisted_9)
              ]),
              _createElementVNode("div", _hoisted_10, [
                _createElementVNode("div", _hoisted_11, [
                  _cache[1] || (_cache[1] = _createElementVNode("label", null, "群组ID", -1)),
                  _withDirectives(_createElementVNode("input", {
                    "onUpdate:modelValue": $event => ((rule.chat_ids) = $event),
                    class: "inp",
                    placeholder: "多个逗号分隔，如 -1001234567,-1007654321"
                  }, null, 8, _hoisted_12), [
                    [_vModelText, rule.chat_ids]
                  ])
                ]),
                _createElementVNode("div", _hoisted_13, [
                  _cache[2] || (_cache[2] = _createElementVNode("label", null, "用户ID", -1)),
                  _withDirectives(_createElementVNode("input", {
                    "onUpdate:modelValue": $event => ((rule.user_ids) = $event),
                    class: "inp",
                    placeholder: "多个逗号分隔"
                  }, null, 8, _hoisted_14), [
                    [_vModelText, rule.user_ids]
                  ])
                ]),
                _createElementVNode("div", _hoisted_15, [
                  _createElementVNode("div", _hoisted_16, [
                    _cache[3] || (_cache[3] = _createElementVNode("label", null, "首句回复", -1)),
                    _withDirectives(_createElementVNode("input", {
                      "onUpdate:modelValue": $event => ((rule.first_reply) = $event),
                      class: "inp",
                      placeholder: "第一句回复内容"
                    }, null, 8, _hoisted_17), [
                      [_vModelText, rule.first_reply]
                    ])
                  ]),
                  _createElementVNode("div", _hoisted_18, [
                    _cache[4] || (_cache[4] = _createElementVNode("label", null, "重置(小时)", -1)),
                    _withDirectives(_createElementVNode("input", {
                      "onUpdate:modelValue": $event => ((rule.reset_hours) = $event),
                      class: "inp",
                      type: "number",
                      min: "0"
                    }, null, 8, _hoisted_19), [
                      [
                        _vModelText,
                        rule.reset_hours,
                        void 0,
                        { number: true }
                      ]
                    ])
                  ])
                ]),
                _createElementVNode("div", _hoisted_20, [
                  _createElementVNode("div", _hoisted_21, [
                    _cache[5] || (_cache[5] = _createElementVNode("label", null, "关键词触发回复", -1)),
                    _createElementVNode("button", {
                      class: "btn sm",
                      onClick: $event => (addTrigger(rule))
                    }, "➕ 添加", 8, _hoisted_22)
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
                      }, null, 8, _hoisted_23), [
                        [_vModelText, tr.keywords]
                      ]),
                      _withDirectives(_createElementVNode("input", {
                        "onUpdate:modelValue": $event => ((tr.replies) = $event),
                        class: "inp",
                        placeholder: "回复内容，逗号分隔"
                      }, null, 8, _hoisted_24), [
                        [_vModelText, tr.replies]
                      ]),
                      _createElementVNode("button", {
                        class: "btn danger sm",
                        onClick: $event => (delTrigger(rule, ti))
                      }, "✕", 8, _hoisted_25)
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
const Config = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-016916ec"]]);

export { Config as default };
