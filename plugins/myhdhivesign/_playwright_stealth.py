"""
Playwright Stealth 反检测模块 v2
使用 CDP 参数 + add_init_script 双重注入
"""

STEALTH_JS = """
// ===== Playwright Stealth Injection =====
// 覆盖 webdriver 检测 — 模拟真实 Chrome 行为
// 真实 Chrome 中 navigator.webdriver 是 Navigator.prototype 上的属性，值 false
// 自动化时 Playwright 在 navigator 自身设置 webdriver=true
// 我们删除自身属性，让原型链上的 false 生效
try {
    delete navigator.webdriver;
} catch(e) {}
// 确保原型链上也返回 false
if (Navigator.prototype) {
    Object.defineProperty(Navigator.prototype, 'webdriver', {
        get: () => false,
        configurable: true,
        enumerable: true,
    });
}

// Chrome 对象
window.chrome = {
    runtime: {
        onMessage: { addListener: () => {} },
        onConnect: { addListener: () => {} },
        onInstalled: { addListener: () => {} },
    },
    loadTimes: () => {},
    csi: () => {},
    app: { isInstalled: false, InstallState: { DISABLED: 'disabled', INSTALLED: 'installed', NOT_INSTALLED: 'not_installed' }, RunningState: { CANNOT_RUN: 'cannot_run', READY_TO_RUN: 'ready_to_run', RUNNING: 'running' } },
};

// Plugins
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai' },
            { name: 'Native Client', filename: 'internal-nacl-plugin' },
        ];
        plugins.item = (i) => plugins[i] || null;
        plugins.namedItem = (n) => plugins.find(p => p.name === n) || null;
        plugins.length = 3;
        return plugins;
    },
    configurable: true,
});

// Languages
Object.defineProperty(navigator, 'languages', {
    get: () => ['zh-CN', 'zh', 'en'],
    configurable: true,
});

// 硬件并发
Object.defineProperty(navigator, 'hardwareConcurrency', {
    get: () => 8,
    configurable: true,
});

// 内存
Object.defineProperty(navigator, 'deviceMemory', {
    get: () => 8,
    configurable: true,
});

// 覆盖权限查询
if (navigator.permissions) {
    const originalQuery = navigator.permissions.query.bind(navigator.permissions);
    navigator.permissions.query = (desc) => {
        if (desc && (desc.name === 'notifications' || desc.name === 'clipboard-read' || desc.name === 'clipboard-write')) {
            return Promise.resolve({ state: 'denied', onchange: null });
        }
        return originalQuery(desc);
    };
    navigator.permissions.query.toString = () => 'function query() { [native code] }';
}
"""

# Playwright 浏览器启动参数 — 禁用自动化检测
STEALTH_LAUNCH_ARGS = [
    "--disable-blink-features=AutomationControlled",
    "--disable-automation",
    "--no-sandbox",
    "--disable-setuid-sandbox",
    "--disable-infobars",
    "--disable-breakpad",
    "--disable-dev-shm-usage",
    "--disable-sync",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-background-timer-throttling",
    "--disable-backgrounding-occluded-windows",
    "--disable-component-extensions-with-background-pages",
    "--disable-extensions",
    "--disable-features=TranslateUI,ChromeWhatsNewUI",
    "--disable-ipc-flooding-protection",
    "--disable-renderer-backgrounding",
    "--disable-search-engine-choice-screen",
    "--disable-session-crashed-bubble",
    "--hide-scrollbars",
    "--metrics-recording-only",
    "--mute-audio",
    "--password-store=basic",
    "--use-mock-keychain",
]


async def create_stealth_context(browser):
    """创建启用了 stealth 的浏览器上下文"""
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
        locale="zh-CN",
        timezone_id="Asia/Shanghai",
        color_scheme="dark",
    )
    # 通过 CDP 注入 stealth 脚本
    await context.add_init_script(STEALTH_JS)
    return context


async def stealth_page(context):
    """在现有 context 中创建 stealth 页面"""
    page = await context.new_page()
    return page


async def test_stealth():
    """全面测试 stealth 效果"""
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # 带 stealth 参数启动
        browser = await p.chromium.launch(
            headless=True,
            args=STEALTH_LAUNCH_ARGS,
        )
        context = await create_stealth_context(browser)
        page = await context.new_page()

        # 检测各项指纹
        checks = {
            "navigator.webdriver": "navigator.webdriver",
            "navigator.plugins.length": "navigator.plugins.length",
            "navigator.languages": "JSON.stringify(navigator.languages)",
            "window.chrome.runtime": "!!window.chrome && !!window.chrome.runtime",
            "navigator.hardwareConcurrency": "navigator.hardwareConcurrency",
            "navigator.deviceMemory": "navigator.deviceMemory",
            "screen.width": "screen.width",
            "screen.height": "screen.height",
            "permissions.notifications": "navigator.permissions.query({name:'notifications'}).then(r => r.state)",
        }

        print("=" * 60)
        print("Stealth 指纹检测结果")
        print("=" * 60)
        for name, js in checks.items():
            try:
                val = await page.evaluate(js)
                status = "✅" if (
                    (name == "navigator.webdriver" and val is False) or
                    (name == "navigator.plugins.length" and val > 0) or
                    ("languages" in name and "zh-CN" in str(val)) or
                    ("chrome" in name and val) or
                    ("Concurrency" in name and val == 8) or
                    ("Memory" in name and val == 8) or
                    ("width" in name and val == 1920) or
                    ("height" in name and val == 1080) or
                    ("permissions" in name and "denied" in str(val))
                ) else "❌"
                print(f"  {status} {name}: {val}")
            except Exception as e:
                print(f"  ⚠️ {name}: {e}")

        # 打开指纹检测页面
        print("\n[TEST] 打开 bot.sannysoft.com...")
        await page.goto("https://bot.sannysoft.com/", wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3000)
        await page.screenshot(path="/tmp/stealth_test_sannysoft.png", full_page=True)
        print("[TEST] 截图: /tmp/stealth_test_sannysoft.png")

        # 再看看页面上的检测结果
        results = await page.evaluate("""
            () => {
                const rows = document.querySelectorAll('tr');
                return Array.from(rows).slice(0, 20).map(r => {
                    const cells = r.querySelectorAll('td');
                    return cells.length >= 2 ? {
                        test: cells[0].textContent.trim(),
                        result: cells[1].textContent.trim()
                    } : null;
                }).filter(Boolean);
            }
        """)
        if results:
            print("\n[TEST] 指纹检测页面结果:")
            for r in results:
                emoji = "❌" if "failed" in r.get('result','').lower() or "missing" in r.get('result','').lower() else "✅"
                print(f"  {emoji} {r['test']}: {r['result']}")

        await browser.close()
        print("\n✅ 测试完成")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_stealth())