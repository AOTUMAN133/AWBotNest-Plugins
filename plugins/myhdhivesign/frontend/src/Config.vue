<script setup>
import { ref, reactive, onMounted } from 'vue'

const props = defineProps({ pluginId: String, host: Object })

const tab = ref('accounts')
const accounts = ref([])
const logs = ref([])
const debugLogs = ref([])
const signing = ref(false)
const refreshing = ref(false)
const loading = ref(true)
const cfg = reactive({ sign_hour: 9, sign_window: 2, sign_minute: 0 })
const statusData = ref({})
const expandedAcc = ref(-1)

function defAcc() {
  return { name: '', username: '', password: '', cookie: '', gamble: false }
}

async function load() {
  try {
    const [r, l, d, config] = await Promise.all([
      props.host.callApi('/get_accounts', 'GET'),
      props.host.callApi('/get_logs', 'GET'),
      props.host.callApi('/get_debug_logs', 'GET'),
      props.host.getConfig(),
    ])
    if (r?.accounts) accounts.value = r.accounts
    if (l?.logs) logs.value = l.logs
    if (d?.logs) debugLogs.value = d.logs
    if (config) {
      cfg.sign_hour = config.sign_hour ?? 9
      cfg.sign_window = config.sign_window ?? 2
      cfg.sign_minute = config.sign_minute ?? 0
    }
    // 从 KV 读取自定义时间配置（覆盖插件配置）
    try {
      const kv = await props.host.callApi('/get_kv', { method: 'GET' })
      if (kv) {
        if (kv.hour !== undefined) cfg.sign_hour = kv.hour
        if (kv.window !== undefined) cfg.sign_window = kv.window
        if (kv.minute !== undefined) cfg.sign_minute = kv.minute
      }
    } catch(e) {}
    await refreshStatus()
  } catch (e) {
    props.host.toast.error('加载失败: ' + (e.message || e))
  } finally {
    loading.value = false
  }
}

function addAcc() { accounts.value.push(defAcc()) }
function delAcc(i) { accounts.value.splice(i, 1) }

async function save() {
  try {
    // 保存时间配置到独立 API（避免平台 saveConfig 覆盖问题）
    const t = await props.host.callApi('/save_time_config', {
      method: 'POST',
      body: { sign_hour: cfg.sign_hour, sign_window: cfg.sign_window, sign_minute: cfg.sign_minute },
    })
    // 保存账号到平台
    await props.host.saveConfig({
      accounts: JSON.stringify(accounts.value),
    })
    if (t?.ok) props.host.toast.success('已保存')
    else props.host.toast.error('保存失败: ' + (t?.message || '未知错误'))
  } catch (e) {
    props.host.toast.error('保存失败: ' + (e.message || e))
  }
}

async function signNow() {
  signing.value = true
  try {
    await props.host.saveConfig({
      accounts: JSON.stringify(accounts.value),
      api_key: undefined,
      user_token: undefined,
    })
    const r = await props.host.callApi('/sign_now', { method: 'POST', body: {} })
    if (r?.ok) props.host.toast.success(r.message)
    else props.host.toast.error(r?.message || '签到失败')
    await load()
  } catch (e) {
    props.host.toast.error('签到出错: ' + (e.message || e))
  } finally {
    signing.value = false
  }
}

async function refreshStatus(idx) {
  refreshing.value = true
  try {
    if (idx !== undefined) {
      // 刷新单个账号
      const a = accounts.value[idx]
      if (!a?.cookie) return
      const r = await props.host.callApi('/get_account_status', { method: 'POST', body: {} })
      if (r?.results && r.results[idx]) {
        const map = { ...statusData.value }
        map[idx] = r.results[idx]
        statusData.value = map
      }
    } else {
      const r = await props.host.callApi('/get_account_status', { method: 'POST', body: {} })
      if (r?.results) {
        const map = {}
        r.results.forEach((s, i) => { map[i] = s })
        statusData.value = map
      }
      props.host.toast.success('状态已刷新')
    }
  } catch (e) {
    // ignore
  } finally {
    refreshing.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="hdhive">
    <div v-if="loading" class="muted">加载中…</div>
    <template v-else>
      <div class="tabs">
        <button :class="['tab', { on: tab === 'accounts' }]" @click="tab='accounts'">📋 账号</button>
        <button :class="['tab', { on: tab === 'logs' }]" @click="tab='logs'">📊 记录</button>
        <button :class="['tab', { on: tab === 'debug' }]" @click="tab='debug'">🔍 日志</button>
      </div>

      <div v-show="tab === 'accounts'">
        <div class="bar">
          <button class="btn primary" :disabled="signing" @click="signNow">{{ signing ? '签到中…' : '▶ 立即签到' }}</button>
          <button class="btn primary" :disabled="refreshing" @click="refreshStatus()">{{ refreshing ? '刷新中…' : '🔄 刷新状态' }}</button>
          <button class="btn primary" @click="save">💾 保存</button>
        </div>

        <div class="time-section">
          <div class="row"><span class="lbl">签到开始</span><input v-model.number="cfg.sign_hour" class="inp sm" type="number" min="0" max="23" /><span class="hint">时</span></div>
          <div class="row"><span class="lbl">签到窗口</span><input v-model.number="cfg.sign_window" class="inp sm" type="number" min="0" max="12" step="0.1" /><span class="hint">小时，0=固定分钟，账号在此窗口内随机分配时间</span></div>
          <div v-if="cfg.sign_window <= 0" class="row"><span class="lbl">签到分钟</span><input v-model.number="cfg.sign_minute" class="inp sm" type="number" min="0" max="59" /><span class="hint">固定分钟（窗口为0时用）</span></div>
        </div>

        <div v-for="(a, i) in accounts" :key="i" class="acc-card">
          <div class="acc-hd" @click="expandedAcc = expandedAcc === i ? -1 : i">
            <div class="acc-info">
              <b>{{ a.name || '未命名' }}</b>
              <div class="acc-stats">
                <span class="stat">⭐ {{ statusData[i]?.points ?? '?' }}</span>
                <span class="stat">📅 {{ statusData[i]?.days ?? '?' }}天</span>
                <span class="stat" :class="statusData[i]?.signed ? 'signed' : ''">{{ statusData[i]?.signed ? '✅ 已签到' : '⏳ 待签到' }}</span>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:6px">
              <span class="expand-icon">{{ expandedAcc === i ? '▲' : '▼' }}</span>
            </div>
          </div>
          <template v-if="expandedAcc === i">
            <div class="acc-body">
              <div class="row"><span class="lbl">别名</span><input v-model="a.name" class="inp" placeholder="可选" /></div>
              <div class="row"><span class="lbl">用户名</span><input v-model="a.username" class="inp" placeholder="或直接填Cookie" /></div>
              <div class="row"><span class="lbl">密码</span><input v-model="a.password" class="inp" type="password" placeholder="留空则用Cookie" /></div>
              <div class="row"><span class="lbl">Cookie</span><input v-model="a.cookie" class="inp" placeholder="登录后自动填充" /></div>
              <label class="sw"><input v-model="a.gamble" type="checkbox" /><span>赌狗签到（参与概率奖池）</span></label>
              <button class="btn sm danger" @click.stop="delAcc(i)">删除账号</button>
            </div>
          </template>
        </div>
        <button class="btn" style="width:100%;margin-top:8px" @click="addAcc">＋ 添加账号</button>
      </div>

      <div v-show="tab === 'logs'">
        <div v-if="!logs.length" class="muted" style="padding:40px 0;text-align:center">暂无签到记录</div>
        <div v-for="log in logs" :key="log.time" class="log">
          <span>{{ log.status }}</span>
          <b>{{ log.name }}</b>
          <span v-if="log.mode" class="tag">{{ log.mode }}</span>
          <span class="msg">{{ log.message }}</span>
          <span class="ts">{{ log.time?.slice(5, 16) }}</span>
        </div>
      </div>

      <div v-show="tab === 'debug'">
        <div v-if="!debugLogs.length" class="muted" style="padding:40px 0;text-align:center">暂无日志</div>
        <div v-for="log in debugLogs" :key="log.t" class="log" style="font-size:12px;font-family:monospace">
          <span class="ts">{{ log.t }}</span>
          <span class="msg">{{ log.m }}</span>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.hdhive { font-size: 14px; color: #e0e0e0; }
.muted { color: #888; }
.tabs { display: flex; gap: 0; border-bottom: 2px solid #333; margin-bottom: 12px; }
.tab { padding: 8px 20px; cursor: pointer; color: #888; font-size: 14px; border: none; background: none; border-bottom: 2px solid transparent; margin-bottom: -2px; }
.tab.on { color: #1677ff; border-bottom-color: #1677ff; font-weight: 600; }
.bar { display: flex; gap: 8px; margin-bottom: 12px; }
.btn { border: 1px solid #444; border-radius: 4px; padding: 5px 14px; cursor: pointer; font-size: 13px; background: #2a2a2a; color: #e0e0e0; }
.btn.primary { background: #1677ff; color: #fff; border-color: #1677ff; }
.btn.sm { padding: 2px 10px; font-size: 12px; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.card { border: 1px solid #333; border-radius: 6px; padding: 12px; margin-bottom: 8px; background: #1e1e1e; }
.card-hd { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.row { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.lbl { width: 52px; font-size: 13px; color: #999; flex-shrink: 0; }
.inp { flex: 1; border: 1px solid #444; border-radius: 4px; padding: 5px 8px; font-size: 13px; outline: none; background: #2a2a2a; color: #e0e0e0; }
.inp:focus { border-color: #1677ff; }
.inp::placeholder { color: #666; }
.sw { display: flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 13px; cursor: pointer; color: #ccc; }
.tag { background: #332; color: #d46b08; border-radius: 3px; padding: 0 6px; font-size: 12px; }
.log { display: flex; gap: 8px; align-items: center; padding: 6px 0; border-bottom: 1px solid #333; font-size: 13px; }
.msg { color: #aaa; }
.ts { color: #555; font-size: 11px; margin-left: auto; }

.acc-card { border: 1px solid var(--border-light, #2a2e3a); border-radius: 10px; margin-bottom: 10px; cursor: pointer; overflow: hidden; background: var(--bg-card, #1a1d27); transition: all 0.2s; }
.acc-card:hover { border-color: var(--accent, #4b89ff); }
.acc-hd { display: flex; justify-content: space-between; align-items: center; padding: 14px; }
.acc-info { flex: 1; min-width: 0; }
.acc-info b { font-size: 15px; color: var(--text-primary, #e8ebf0); display: block; margin-bottom: 2px; }
.acc-stats { display: flex; gap: 14px; font-size: 12px; }
.acc-stats .stat { color: var(--text-secondary, #b9c0cc); }
.acc-stats .signed { color: #4caf50; font-weight: 500; }
.expand-icon { color: var(--text-muted, #7a8291); font-size: 11px; }
.acc-body { border-top: 1px solid var(--border-light, #2a2e3a); padding: 14px; }

.time-section { background: var(--bg-card, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); border-radius: 10px; padding: 12px; margin-bottom: 10px; }
.time-section .row { margin-bottom: 6px; }
.time-section .hint { font-size: 12px; color: var(--text-muted, #7a8291); margin-left: 6px; }
</style>