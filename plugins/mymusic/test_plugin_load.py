"""
插件加载测试 - 模拟平台 importlib 加载方式
用于在提交给用户前发现路径/导入问题
"""
import sys, os, importlib, json

def test_plugin_load():
    """测试插件能否被平台正确加载（不添加插件目录到 sys.path）"""
    plugin_path = os.path.join(os.path.dirname(__file__), '__init__.py')
    plugin_dir = os.path.dirname(plugin_path)
    
    print(f'测试插件: {plugin_path}')
    print(f'插件目录: {plugin_dir}')
    
    # 确保插件目录不在 sys.path 中
    sys.path = [p for p in sys.path if plugin_dir not in p and os.path.abspath(p) != os.path.abspath(plugin_dir)]
    
    # 使用 importlib 加载（与平台一致）
    spec = importlib.util.spec_from_file_location('test_plugin', plugin_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    
    # 检查元数据
    meta = mod.__plugin__
    assert meta.get('name'), '缺少插件名'
    assert meta.get('version'), '缺少版本号'
    assert meta.get('id'), '缺少插件ID'
    print(f'  ✅ 元数据: {meta["name"]} v{meta["version"]}')
    
    # 检查 setup 函数
    assert hasattr(mod, 'setup'), '缺少 setup 函数'
    assert hasattr(mod, 'teardown'), '缺少 teardown 函数'
    print(f'  ✅ setup/teardown 存在')
    
    # 检查 _musicdl_search_sync 导入（通过函数，不实际搜索）
    print(f'  🔍 测试 _musicdl_search_sync 函数调用...')
    try:
        # 不传 keyword 触发异常，但导入应该成功
        # 这会触发函数内的 sys.path 修复 + from _musicdl_wrapper import ...
        result = mod._musicdl_search_sync('', ['netease'])
        print(f'  ✅ _musicdl_search_sync 调用成功（返回空列表）')
    except ImportError as e:
        print(f'  ❌ _musicdl_search_sync 导入失败: {e}')
        print(f'  💡 需要在 _musicdl_search_sync 中添加 sys.path 修复')
        return False
    except Exception as e:
        # 非 ImportError 异常（如搜索超时/无结果）说明导入成功了
        print(f'  ✅ _musicdl_search_sync 导入成功（函数调用异常: {type(e).__name__}）')
        pass
    
    # 检查所有辅助函数
    for func_name in ['_musicdl_search_sync', '_musicdl_url_sync', '_build_result_page', '_format_duration', '_yt_path']:
        fn = getattr(mod, func_name, None)
        assert fn is not None, f'缺少 {func_name}'
    print(f'  ✅ 辅助函数全部存在')
    
    print(f'\n✅ 插件加载测试通过')
    return True

if __name__ == '__main__':
    success = test_plugin_load()
    sys.exit(0 if success else 1)