#!/usr/bin/env python3
"""
AWBotNest 平台模拟测试环境
使用与平台一致的 Python 3.13 + 相同依赖，模拟 importlib 加载方式
"""
import os
import sys
import json
import importlib
import importlib.util
import traceback

# 测试结果
PASS = 0
FAIL = 0

def test(name, fn):
    global PASS, FAIL
    try:
        fn()
        print(f"  ✅ {name}")
        PASS += 1
    except Exception as e:
        print(f"  ❌ {name}: {e}")
        traceback.print_exc()
        FAIL += 1


def load_plugin(plugin_dir: str):
    """模拟平台加载插件的方式"""
    init_path = os.path.join(plugin_dir, "__init__.py")
    if not os.path.isfile(init_path):
        raise FileNotFoundError(f"找不到 {init_path}")
    
    # 不添加插件目录到 sys.path（模拟平台行为）
    mod_name = os.path.basename(plugin_dir)
    spec = importlib.util.spec_from_file_location(mod_name, init_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plugin(plugin_dir: str):
    """完整测试一个插件"""
    global PASS, FAIL
    print(f"\n{'='*60}")
    print(f"  测试插件: {os.path.basename(plugin_dir)}")
    print(f"  目录: {plugin_dir}")
    print(f"  环境: Python {sys.version.split()[0]}")
    print(f"{'='*60}\n")
    
    # 1. 加载插件
    mod = None
    def _load():
        nonlocal mod
        mod = load_plugin(plugin_dir)
        meta = mod.__plugin__
        assert meta.get("name"), "缺少插件名"
        assert meta.get("version"), "缺少版本号"
        print(f"    插件: {meta['name']} v{meta['version']}")
        print(f"    依赖: {meta.get('requirements', [])}")
    test("插件加载", _load)
    if not mod:
        return
    
    # 2. 检查 setup/teardown
    test("setup/teardown 存在", lambda: (
        hasattr(mod, "setup") and hasattr(mod, "teardown")
    ))
    
    # 3. 检查依赖是否可导入
    reqs = mod.__plugin__.get("requirements", [])
    for req in reqs:
        # 提取包名（去掉版本号）
        pkg = req.split(">=")[0].split("==")[0].split("<")[0].strip()
        def _check_import(pkg=pkg):
            __import__(pkg.replace("-", "_"))
        test(f"依赖导入: {pkg}", _check_import)
    
    # 4. 测试模块内函数导入
    if hasattr(mod, "_musicdl_search_sync"):
        # 测试函数是否存在
        test("_musicdl_search_sync 存在", lambda: callable(mod._musicdl_search_sync))
        
        # 测试导入（不实际搜索）
        def _test_import():
            # 模拟调用，只测试导入路径
            try:
                mod._musicdl_search_sync("", [])
            except Exception as e:
                # 非 ImportError 说明导入成功
                assert not isinstance(e, ImportError), f"导入失败: {e}"
        test("musicdl 导入测试", _test_import)
    
    print(f"\n  📊 结果: {PASS} 通过, {FAIL} 失败")


if __name__ == "__main__":
    plugin_dir = sys.argv[1] if len(sys.argv) > 1 else "/root/本地插件/mymusic"
    test_plugin(plugin_dir)
    print(f"\n{'='*60}")
    print(f"  总结果: {PASS} 通过 | {FAIL} 失败")
    print(f"{'='*60}")
    sys.exit(0 if FAIL == 0 else 1)