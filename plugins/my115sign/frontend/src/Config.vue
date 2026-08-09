<script setup>
// 115签到 · 配置/管理界面（模块联邦暴露为 ./Config）。
// 平台注入 props { pluginId, host }；host: getConfig/saveConfig/callApi/toast。
// 三个页签：配置（签到时间/扫码设备/推送）/ 账号（扫码Cookie列表）/ 日志。
import { ref, reactive, onMounted } from 'vue'

const props = defineProps({
  pluginId: { type: String, required: true },
  host: { type: Object, required: true },
})

const DEFAULTS = {
  cookies: '',
  scan_device: 'alipaymini',
  scan_timeout: 120,
  wxpusher_spt: '',
  notify_on_sign: false,
  checkin_hour: 9,
  checkin_minute: 0,
}

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
]

const tab = ref('config')
const loading = ref(true)
const saving = ref(false)
const signing = ref(false)
const cfg = reactive({ ...DEFAULTS })

// 账号
const cookies = ref([])
const accLoading = ref(false)

// 日志
const logs = ref([])
const logLoading = ref(false)

// 状态
const statusData = ref({})

onMounted(async () => {
  try {
    const saved = await props.host.getConfig()
    Object.assign(cfg, DEFAULTS, saved || {})
  } catch (e) {
    props.host.toast.error('读取配置失败：' + (e.message || e))
  } finally {
    loading.value = false
  }
})

async function save() {
  saving.value = true
  try {
    await props.host.saveConfig({ ...cfg })
    props.host.toast.success('配置已保存')
  } catch (e) {
    props.host.toast.error('保存失败：' + (e.message || e))
  } finally {
    saving.value = false
  }
}

async function signNow() {
  signing.value = true
  try {
    // 先保存配置再签到
    await props.host.saveConfig({ ...cfg })
    const r = await props.host.callApi('/sign_now', { method: 'POST', body: {} })
    if (r?.ok) {
      props.host.toast.success(r.message || '签到完成')
      // 刷新日志和状态
      await loadLogs()
      await loadStatus()
    } else {
      props.host.toast.error(r?.message || '签到失败')
    }
  } catch (e) {
    props.host.toast.error('签到出错：' + (e.message || e))
  } finally {
    signing.value = false
  }
}

async function loadStatus() {
  try {
    const r = await props.host.callApi('/status', { method: 'GET' })
    if (r?.ok) {
      statusData.value = r
    }
  } catch (e) {
    // 静默
  }
}

async function loadCookies() {
  accLoading.value = true
  try {
    const r = await props.host.callApi('/cookies', { method: 'GET' })
    if (r?.ok) {
      cookies.value = r.cookies || []
    }
  } catch (e) {
    props.host.toast.error('读取账号失败：' + (e.message || e))
  } finally {
    accLoading.value = false
  }
}

async function deleteCookie(uid) {
  if (!confirm(`确定删除账号 UID=${uid} 的 Cookie？`)) return
  try {
    const r = await props.host.callApi('/delete_cookie', { method: 'POST', body: { uid } })
    if (r?.ok) {
      props.host.toast.success('已删除')
      await loadCookies()
    } else {
      props.host.toast.error(r?.message || '删除失败')
    }
  } catch (e) {
    props.host.toast.error('删除失败：' + (e.message || e))
  }
}

async function loadLogs() {
  logLoading.value = true
  try {
    const r = await props.host.callApi('/logs', { method: 'GET' })
    if (r?.ok) {
      logs.value = r.logs || []
    }
  } catch (e) {
    props.host.toast.error('读取日志失败：' + (e.message || e))
  } finally {
    logLoading.value = false
  }
}

function switchTab(t) {
  tab.value = t
  if (t === 'accounts' && !cookies.value.length) loadCookies()
  if (t === 'logs' && !logs.value.length) loadLogs()
}

function deviceLabel(val) {
  const d = DEVICE_OPTIONS.find(x => x.value === val)
  return d ? d.label : val
}
</script>

<template>
  <div class="sign115">
    <div v-if="loading" class="muted">加载配置…</div>
    <template v-else>
      <div class="tabs">
        <button :class="['tab', { on: tab === 'config' }]" @click="switchTab('config')">⚙ 配置</button>
        <button :class="['tab', { on: tab === 'accounts' }]" @click="switchTab('accounts')">📱 账号</button>
        <button :class="['tab', { on: tab === 'logs' }]" @click="switchTab('logs')">📊 日志</button>
      </div>

      <!-- ============ 配置 ============ -->
      <div v-show="tab === 'config'" class="pane">
        <!-- 定时签到 -->
        <section class="card">
          <h3 class="card-title">⏰ 定时签到</h3>
          <div class="row">
            <span class="lbl">签到时间</span>
            <span class="val">{{ String(cfg.checkin_hour).padStart(2, '0') }}:{{ String(cfg.checkin_minute).padStart(2, '0') }}</span>
          </div>
          <div class="row">
            <span class="lbl">小时</span>
            <input type="range" v-model.number="cfg.checkin_hour" min="0" max="23" step="1" class="slider" />
            <span class="hint">{{ cfg.checkin_hour }} 时</span>
          </div>
          <div class="row">
            <span class="lbl">分钟</span>
            <input type="range" v-model.number="cfg.checkin_minute" min="0" max="59" step="1" class="slider" />
            <span class="hint">{{ cfg.checkin_minute }} 分</span>
          </div>
        </section>

        <!-- 扫码登录 -->
        <section class="card">
          <h3 class="card-title">📱 扫码登录</h3>
          <div class="row">
            <span class="lbl">设备类型</span>
            <select v-model="cfg.scan_device" class="inp">
              <option v-for="d in DEVICE_OPTIONS" :key="d.value" :value="d.value">{{ d.label }}</option>
            </select>
          </div>
          <div class="row">
            <span class="lbl">扫码超时</span>
            <input v-model.number="cfg.scan_timeout" class="inp sm" type="number" min="30" max="300" />
            <span class="hint">秒（30~300）</span>
          </div>
          <p class="tip">💡 扫码登录请在聊天中发送 <code>.115login</code>，选择设备后用 115 APP 扫码。推荐使用「115生活(支付宝小程序)」，Cookie 不易失效。</p>
        </section>

        <!-- 推送 -->
        <section class="card">
          <h3 class="card-title">🔔 推送通知</h3>
          <label class="row switch">
            <input v-model="cfg.notify_on_sign" type="checkbox" />
            <span>WxPusher 推送签到结果</span>
          </label>
          <p class="tip">开启后，签到结果会推送到 WxPusher（需配置下方 SPT）。平台内通知（TG/飞书）始终发送，不受此开关控制。</p>
          <div class="row top">
            <span class="lbl">WxPusher SPT</span>
            <textarea v-model="cfg.wxpusher_spt" class="inp" rows="2" placeholder="WxPusher 推送令牌，留空则不推送。多个用逗号或换行分隔。"></textarea>
          </div>
        </section>

        <!-- 操作 -->
        <div class="bar">
          <button class="btn primary" :disabled="signing" @click="signNow">{{ signing ? '签到中…' : '▶ 立即签到' }}</button>
          <button class="btn" :disabled="saving" @click="save">{{ saving ? '保存中…' : '💾 保存配置' }}</button>
        </div>
      </div>

      <!-- ============ 账号 ============ -->
      <div v-show="tab === 'accounts'" class="pane">
        <div class="toolbar">
          <span class="muted">扫码登录的账号（共 {{ cookies.length }} 个）</span>
          <span class="grow"></span>
          <button class="btn" @click="loadCookies">🔄 刷新</button>
        </div>

        <div v-if="accLoading" class="muted center">加载中…</div>
        <div v-else-if="!cookies.length" class="empty">
          暂无扫码登录的账号<br>
          <span class="muted">扫码登录请在聊天中发送 <code>.115login</code></span>
        </div>
        <div v-else class="acc-list">
          <div v-for="(c, i) in cookies" :key="i" class="acc-card">
            <div class="acc-info">
              <span class="acc-icon">👤</span>
              <div class="acc-detail">
                <div class="acc-uid">UID: {{ c.uid }}</div>
                <div class="acc-sub">扫码登录账号 #{{ i + 1 }}</div>
              </div>
            </div>
            <button class="btn sm danger" @click="deleteCookie(c.uid)">删除</button>
          </div>
        </div>

        <div class="hint-box">
          💡 扫码登录请在聊天中发送 <code>.115login</code>，选择设备后用 115 APP 扫码即可自动添加 Cookie。
        </div>
      </div>

      <!-- ============ 日志 ============ -->
      <div v-show="tab === 'logs'" class="pane">
        <div class="toolbar">
          <span class="muted">运行日志</span>
          <span class="grow"></span>
          <button class="btn" @click="loadLogs">🔄 刷新</button>
        </div>
        <div v-if="logLoading" class="muted center">加载中…</div>
        <div v-else-if="!logs.length" class="empty">
          暂无日志<br>
          <span class="muted">签到后日志会在这里显示</span>
        </div>
        <div v-else class="log-list">
          <div v-for="(log, i) in logs" :key="i" class="log-item">
            <span class="log-time">{{ log.t }}</span>
            <span class="log-msg">{{ log.m }}</span>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.sign115 { display: flex; flex-direction: column; gap: 14px; container-type: inline-size; }
.tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border-light, #2a2e3a); }
.tab { padding: 8px 16px; background: none; border: none; cursor: pointer; font-size: 13px; color: var(--text-secondary, #b9c0cc); border-bottom: 2px solid transparent; }
.tab.on { color: var(--accent, #6ea8fe); border-bottom-color: var(--accent, #6ea8fe); }

.pane { display: flex; flex-direction: column; gap: 14px; }
.card { display: flex; flex-direction: column; gap: 12px; padding: 16px; border-radius: 10px; background: var(--bg-elevated, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); }
.card-title { margin: 0; font-size: 15px; font-weight: 600; color: var(--text-primary, #e8ebf0); }

.row { display: flex; align-items: center; gap: 10px; }
.row.top { align-items: flex-start; }
.row > .lbl { min-width: 72px; font-size: 13px; color: var(--text-secondary, #b9c0cc); flex-shrink: 0; }
.row > .val { font-size: 14px; font-weight: 600; color: var(--accent, #6ea8fe); }
.row.switch { justify-content: flex-start; cursor: pointer; }
.row.switch span { min-width: 0; font-size: 13px; color: var(--text-primary, #e8ebf0); }
.hint { font-size: 12px; color: var(--text-muted, #7a8291); white-space: nowrap; }
.tip { margin: 0; font-size: 12px; color: var(--text-muted, #7a8291); line-height: 1.6; }
.tip code, .hint-box code { background: var(--bg-card, #12141c); padding: 1px 5px; border-radius: 3px; font-size: 12px; color: var(--accent, #6ea8fe); }

.inp { flex: 1; min-width: 0; padding: 8px 10px; border-radius: 6px; font-size: 13px; background: var(--bg-card, #12141c); color: var(--text-primary, #e8ebf0); border: 1px solid var(--border-light, #2a2e3a); }
.inp.sm { flex: 0 0 auto; width: 90px; }
textarea.inp { resize: vertical; font-family: inherit; line-height: 1.5; }
select.inp { cursor: pointer; }

.slider { flex: 1; max-width: 200px; height: 6px; cursor: pointer; accent-color: var(--accent, #6ea8fe); }

.btn { padding: 7px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--bg-card, #12141c); color: var(--text-secondary, #b9c0cc); border: 1px solid var(--border-light, #2a2e3a); }
.btn:hover { border-color: var(--accent, #6ea8fe); color: var(--accent, #6ea8fe); }
.btn.primary { background: var(--accent-dim, #1e3a5f); border-color: var(--accent, #6ea8fe); color: var(--accent, #6ea8fe); }
.btn.danger:hover { border-color: #ff6b6b; color: #ff6b6b; }
.btn.sm { padding: 4px 10px; font-size: 12px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }

.bar { display: flex; gap: 10px; }

.toolbar { display: flex; align-items: center; gap: 8px; }
.grow { flex: 1; }
.muted { font-size: 12px; color: var(--text-muted, #7a8291); }
.muted.center { text-align: center; padding: 40px 0; }
.empty { text-align: center; padding: 48px 0; font-size: 15px; color: var(--text-secondary, #b9c0cc); }
.empty code { background: var(--bg-card, #12141c); padding: 1px 5px; border-radius: 3px; font-size: 13px; color: var(--accent, #6ea8fe); }

/* 账号列表 */
.acc-list { display: flex; flex-direction: column; gap: 8px; }
.acc-card { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-radius: 8px; background: var(--bg-elevated, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); }
.acc-card:hover { border-color: var(--accent, #6ea8fe); }
.acc-info { display: flex; align-items: center; gap: 10px; }
.acc-icon { font-size: 20px; }
.acc-detail { display: flex; flex-direction: column; gap: 2px; }
.acc-uid { font-size: 14px; color: var(--text-primary, #e8ebf0); font-weight: 500; }
.acc-sub { font-size: 12px; color: var(--text-muted, #7a8291); }

.hint-box { padding: 12px 14px; border-radius: 8px; background: var(--bg-elevated, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); font-size: 12px; color: var(--text-muted, #7a8291); line-height: 1.6; }

/* 日志列表 */
.log-list { display: flex; flex-direction: column; gap: 2px; max-height: 500px; overflow-y: auto; }
.log-item { display: flex; gap: 10px; align-items: flex-start; padding: 8px 12px; border-bottom: 1px solid var(--border-light, #2a2e3a); font-size: 13px; }
.log-item:hover { background: var(--bg-elevated, #1a1d27); }
.log-time { color: var(--text-muted, #7a8291); font-size: 12px; font-family: monospace; flex-shrink: 0; min-width: 60px; }
.log-msg { color: var(--text-secondary, #b9c0cc); word-break: break-word; }

@container (max-width: 620px) {
  .row > .lbl { min-width: 60px; }
  .slider { max-width: 120px; }
  .bar { flex-direction: column; }
  .bar .btn { width: 100%; }
}
</style>
