<template>
  <div class="mm">
    <div class="tabs">
      <button :class="['tab', { on: tab === 'settings' }]" @click="tab = 'settings'">⚙ 设置</button>
      <button :class="['tab', { on: tab === 'status' }]" @click="loadStatus(); tab = 'status'">📊 状态</button>
      <button :class="['tab', { on: tab === 'logs' }]" @click="loadLogs(); tab = 'logs'">📝 记录</button>
    </div>

    <div v-show="tab === 'settings'" class="layout">
      <section class="card">
        <h3>TMDB</h3>
        <label class="row"><span>API Key</span><input v-model="cfg.tmdb_api_key" class="inp" type="password" placeholder="必填" /></label>
        <label class="row"><span>语言</span><input v-model="cfg.tmdb_language" class="inp" placeholder="zh-CN" /></label>
      </section>
      <section class="card">
        <h3>Emby</h3>
        <label class="row"><span>地址</span><input v-model="cfg.emby_url" class="inp" placeholder="http://emby.local:8096" /></label>
        <label class="row"><span>API Key</span><input v-model="cfg.emby_api_key" class="inp" type="password" /></label>
        <label class="row switch"><input v-model="cfg.skip_emby_check" type="checkbox" /><span>跳过 Emby 查重</span></label>
        <label class="row"><span>查重方式</span>
          <select v-model="cfg.emby_check_mode" class="inp" :disabled="cfg.skip_emby_check">
            <option value="realtime">实时查询(逐条)</option>
            <option value="cache">缓存(全量拉取)</option>
          </select>
        </label>
      </section>
      <section class="card">
        <h3>转发</h3>
        <label class="row"><span>目标</span><input v-model="cfg.cms_bot_username" class="inp" placeholder="如 @cmsbot 或 me" /></label>
        <label class="row"><span>标签</span><input v-model="cfg.forward_label" class="inp" placeholder="115 网盘" /></label>
        <label class="row switch"><input v-model="cfg.forward_to_saved" type="checkbox" /><span>转发到收藏夹</span></label>
      </section>
      <section class="card">
        <h3>过滤</h3>
        <div class="fld">
          <span class="lbl">转存类型</span>
          <div class="chips">
            <label class="chip"><input type="checkbox" :checked="mediaTypesArr.includes('movie')" @change="toggleMedia('movie')" /> 电影</label>
            <label class="chip"><input type="checkbox" :checked="mediaTypesArr.includes('tv')" @change="toggleMedia('tv')" /> 电视剧</label>
          </div>
        </div>
        <label class="row switch"><input v-model="cfg.only_complete_series" type="checkbox" /><span>剧集仅转存完结</span></label>
      </section>
            <section class="card">
        <h3>115 网盘</h3>
        <label class="row"><span>Cookie</span><input v-model="cfg.pan115_cookie" class="inp" type="password" placeholder="可选" /></label>
      </section>
      <section class="card">
        <h3>排除类型</h3>
        <p class="tip">勾选后匹配到该类型的资源自动跳过不转发。动画按产地细分：国漫/日漫/美漫/其他，国语配音的国外动画不会误杀。</p>
        <div class="genre-grid">
          <div v-for="g in genreList" :key="g.en" class="chip" :class="{ on: excludeSet.has(g.en.toLowerCase()) }" @click="toggleGenre(g)">
            <span>{{ g.cn }}</span>
          </div>
        </div>
      </section>
            <section class="card">
        <h3>📡 历史扫描</h3>
        <label class="row"><span>来源频道</span><input v-model="cfg.source_chat" class="inp" type="number" placeholder="频道ID" /></label>
        <label class="row"><span>间隔(秒)</span><input v-model="cfg.delay" class="inp" type="number" placeholder="2" /></label>
        <label class="row"><span>每批条数</span><input v-model="cfg.batch_size" class="inp" type="number" placeholder="200" /></label>
        <div class="row"><span>状态</span><b>{{ scanStatus }}</b></div>
        <div class="row" style="gap: 8px;">
          <button class="btn primary" :disabled="scanning" @click="startScan">▶ 开始扫描</button>
          <button class="btn" :disabled="!scanning" @click="stopScan">⏹ 停止</button>
          <button class="btn" @click="resetScan">🔄 重置</button>
        </div>
      </section>
      <section class="card">
        <h3>📦 Emby 缓存</h3>
        <div class="row"><span>缓存状态</span><b>{{ cacheStatus }}</b></div>
        <div class="row" style="gap: 8px;">
          <button class="btn" :disabled="buildingCache" @click="buildCache">📥 建立缓存</button>
        </div>
      </section>
      <div class="savebar"><button class="btn primary lg" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存配置' }}</button></div>
    </div>

    <div v-show="tab === 'status'" class="pane">
      <div class="card">
        <div class="kv"><span>TMDB</span><b :class="s.tmdb_ok ? 'ok' : 'err'">{{ s.tmdb_status || '未检测' }}</b></div>
        <div class="kv"><span>Emby</span><b :class="s.emby_ok ? 'ok' : 'err'">{{ s.emby_status || '未检测' }}</b></div>
        <div class="kv"><span>Emby 库</span><b>{{ s.emby_items ?? '-' }} 项</b></div>
      </div>
      <button class="btn" :disabled="testing" @click="testServices">{{ testing ? '测试中…' : '测试连接' }}</button>
      <p v-if="testMsg" :class="['test-msg', testOk ? 'ok' : 'err']">{{ testMsg }}</p>
    </div>

    <div v-show="tab === 'logs'" class="pane">
      <div class="toolbar"><button class="btn" @click="loadLogs">刷新</button><span class="muted">{{ logs.length }} 条</span></div>
      <table v-if="logs.length" class="tbl">
        <thead><tr><th>时间</th><th>标题</th><th>TMDB</th><th>操作</th></tr></thead>
        <tbody>
          <tr v-for="(l, i) in logs" :key="i">
            <td class="muted">{{ l.time }}</td><td>{{ l.title }}</td>
            <td><code>{{ l.tmdb_id || '-' }}</code></td>
            <td><span :class="'tag-' + l.action">{{ l.action }}</span></td>
          </tr>
        </tbody>
      </table>
      <div v-else class="empty muted">暂无处理记录</div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, watch } from 'vue'

const props = defineProps({ pluginId: String, host: Object })
const tab = ref('settings')
const saving = ref(false)
const testing = ref(false)
const s = reactive({})
const testMsg = ref('')
const testOk = ref(false)
const logs = ref([])
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
})

const mediaTypesArr = ref([])
// 同步 cfg.media_types → mediaTypesArr
watch(() => cfg.media_types, (v) => {
  if (Array.isArray(v)) mediaTypesArr.value = [...v]
  else if (typeof v === 'string' && v) mediaTypesArr.value = v.split(',').filter(Boolean)
  else mediaTypesArr.value = ['movie', 'tv']
}, { immediate: true })

function toggleMedia(type) {
  const arr = [...mediaTypesArr.value]
  const i = arr.indexOf(type)
  if (i >= 0) arr.splice(i, 1); else arr.push(type)
  mediaTypesArr.value = arr
  cfg.media_types = arr.join(',')
}

onMounted(async () => {
  try {
    const saved = await props.host.getConfig()
    Object.assign(cfg, saved || {})
  } catch (e) {
    props.host.toast.error('读取配置失败：' + (e.message || e))
  }
})

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
]
const excludeSet = computed(() => {
  const raw = (cfg.exclude_genres || '').toLowerCase()
  return new Set(raw.split(',').map(s => s.trim()).filter(Boolean))
})
function toggleGenre(g) {
  const raw = (cfg.exclude_genres || '').trim()
  const arr = raw ? raw.split(',').map(s => s.trim()).filter(Boolean) : []
  const key = g.en.toLowerCase()
  const i = arr.indexOf(key)
  if (i >= 0) arr.splice(i, 1); else arr.push(key)
  cfg.exclude_genres = arr.join(',')
}

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

async function loadStatus() {
  try {
    const r = await props.host.callApi('/status')
    Object.assign(s, r || {})
  } catch {}
}

async function testServices() {
  testing.value = true; testMsg.value = ''
  try {
    const r = await props.host.callApi('/test', { method: 'POST', body: {} })
    testOk.value = r.ok; testMsg.value = r.message || ''
    await loadStatus()
  } catch (e) {
    testOk.value = false; testMsg.value = e.message || '测试失败'
  } finally { testing.value = false }
}


const scanning = ref(false)
const scanStatus = ref('就绪')
const buildingCache = ref(false)
const cacheStatus = ref('就绪')

async function buildCache() {
  buildingCache.value = true; cacheStatus.value = '建立中…'
  try {
    const r = await props.host.callApi('/build_cache', { method: 'POST' })
    cacheStatus.value = r.status || '完成'
  } catch (e) { cacheStatus.value = e.message || '建立失败' }
  finally { buildingCache.value = false }
}

async function checkCacheStatus() {
  try {
    const r = await props.host.callApi('/cache_status')
    if (r) cacheStatus.value = r.status || '就绪'
  } catch {}
}
checkCacheStatus()

async function startScan() {
  scanning.value = true; scanStatus.value = '扫描中…'
  try {
    const r = await props.host.callApi('/start_scan', { method: 'POST' })
    if (!r.ok) { scanStatus.value = r.message || '启动失败'; scanning.value = false }
  } catch (e) { scanStatus.value = e.message || '启动失败'; scanning.value = false }
}
async function stopScan() {
  await props.host.callApi('/stop_scan', { method: 'POST' })
  scanning.value = false; scanStatus.value = '已停止'
}
async function resetScan() {
  await props.host.callApi('/reset_scan', { method: 'POST' })
  scanning.value = false; scanStatus.value = '已重置'
}
let statusTimer
onMounted(() => {
  async function checkScanStatus() {
    try {
      const r = await props.host.callApi('/scan_status')
      if (r) {
        scanStatus.value = r.status || '就绪'
        scanning.value = r.running || false
      }
    } catch {}
  }
  checkScanStatus()
  statusTimer = setInterval(checkScanStatus, 5000)
})

async function loadLogs() {
  try {
    const r = await props.host.callApi('/logs')
    logs.value = (r && r.logs) || []
  } catch {}
}
</script>

<style scoped>
.mm { display: flex; flex-direction: column; gap: 14px; container-type: inline-size; }
.tabs { display: flex; gap: 6px; border-bottom: 1px solid var(--border-light, #2a2e3a); }
.tab { padding: 8px 16px; background: none; border: none; cursor: pointer; font-size: 13px; color: var(--text-secondary, #b9c0cc); border-bottom: 2px solid transparent; }
.tab.on { color: var(--accent, #6ea8fe); border-bottom-color: var(--accent, #6ea8fe); }
.layout { display: flex; flex-direction: column; gap: 14px; }
.pane { display: flex; flex-direction: column; gap: 14px; }
.card { display: flex; flex-direction: column; gap: 12px; padding: 16px; border-radius: 10px; background: var(--bg-elevated, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); }
.card h3 { margin: 0; font-size: 14px; font-weight: 600; color: var(--text-primary, #e8ebf0); }
.row { display: flex; align-items: center; gap: 10px; }
.row.switch { justify-content: flex-start; }
.row.switch.big { padding: 12px; margin-bottom: 8px; background: var(--bg-elevated, #1a1d27); border: 1px solid var(--border-light, #2a2e3a); border-radius: 10px; }
.row.top { align-items: flex-start; }
.row > span:first-child { min-width: 80px; font-size: 13px; color: var(--text-secondary, #b9c0cc); }
.fld { display: flex; flex-direction: column; gap: 6px; }
.lbl { font-size: 13px; color: var(--text-secondary, #b9c0cc); }
.chips { display: flex; gap: 8px; }
.chip { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; cursor: pointer; padding: 4px 10px; border-radius: 6px; background: var(--bg-card, #12141c); border: 1px solid var(--border-light, #2a2e3a); color: var(--text-secondary, #b9c0cc); }
.inp { flex: 1; padding: 8px 10px; border-radius: 6px; font-size: 13px; background: var(--bg-card, #12141c); color: var(--text-primary, #e8ebf0); border: 1px solid var(--border-light, #2a2e3a); }
.btn { padding: 7px 14px; border-radius: 6px; cursor: pointer; font-size: 13px; background: var(--bg-card, #12141c); color: var(--text-secondary, #b9c0cc); border: 1px solid var(--border-light, #2a2e3a); }
.btn:hover { border-color: var(--accent, #6ea8fe); color: var(--accent, #6ea8fe); }
.btn.primary { background: var(--accent-dim, #1e3a5f); border-color: var(--accent, #6ea8fe); color: var(--accent, #6ea8fe); }
.btn.lg { padding: 9px 22px; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
.savebar { display: flex; justify-content: flex-end; }
.kv { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--border-light, #2a2e3a); font-size: 13px; }
.kv:last-child { border-bottom: none; }
.kv .ok { color: #4ade80; }
.kv .err { color: #ff6b6b; }
.test-msg { padding: 10px; border-radius: 6px; font-size: 13px; }
.test-msg.ok { background: rgba(74, 222, 128, 0.1); color: #4ade80; }
.test-msg.err { background: rgba(255, 107, 107, 0.1); color: #ff6b6b; }
.toolbar { display: flex; align-items: center; gap: 8px; }
.muted { font-size: 12px; color: var(--text-muted, #7a8291); }
.empty { text-align: center; padding: 40px 0; }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--border-light, #2a2e3a); color: var(--text-secondary, #b9c0cc); font-weight: normal; }
.tbl td { padding: 10px 12px; border-bottom: 1px solid var(--border-light, #2a2e3a); color: var(--text-primary, #e8ebf0); }
code { color: var(--accent, #6ea8fe); font-family: monospace; }
.tag-转发 { color: #4ade80; }
.tag-跳过 { color: #ffa500; }
.tag-Emby已有 { color: #4ade80; }
.tag-Emby未命中 { color: #6ea8fe; }
.tag-Emby查询失败 { color: #ff6b6b; }
.tag-Emby未配置跳过查重 { color: #7a8291; }
.tag-已跳过查重 { color: #ffa500; }
.genre-grid { display: flex; flex-wrap: wrap; gap: 6px; }
.genre-grid .chip { display: flex; align-items: center; gap: 4px; font-size: 11px; cursor: pointer; padding: 6px 10px; border-radius: 8px; background: var(--bg-card, #12141c); border: 1px solid var(--border-light, #2a2e3a); color: var(--text-secondary, #b9c0cc); transition: all .15s; }
.genre-grid .chip.on { background: var(--accent-dim, #1e3a5f); border-color: var(--accent, #6ea8fe); color: var(--accent, #6ea8fe); }
.genre-grid .chip input { display: none; }
.genre-grid .chip span { line-height: 1.3; }
.genre-grid .chip small { opacity: 0.6; font-weight: normal; }
.tip { margin: 0; font-size: 12px; color: var(--text-muted, #7a8291); line-height: 1.6; }
</style>