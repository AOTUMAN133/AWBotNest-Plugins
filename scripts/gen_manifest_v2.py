#!/usr/bin/env python3
"""扫描 AOTUMAN133/AWBotNest-Plugins 所有插件, 生成 manifest_v2.json
V2 规范: 顶层 {"plugins": {id: {...}}}, version 必须与插件 __plugin__ 一致
"""
import ast, json, os, re, sys

REPO_ROOT = '/root/AWBotNest-Plugins'
OUT = os.path.join(REPO_ROOT, 'manifest_v2.json')
BASE_URL = 'https://raw.githubusercontent.com/AOTUMAN133/AWBotNest-Plugins/main'

def find_plugin_meta(path):
    """从单文件或目录 __init__.py 提取 __plugin__"""
    candidates = []
    if path.endswith('.py'):
        candidates.append(path)
    else:
        candidates.append(os.path.join(path, '__init__.py'))
    for c in candidates:
        if not os.path.exists(c):
            continue
        src = open(c, encoding='utf-8', errors='ignore').read()
        try:
            tree = ast.parse(src)
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    for t in node.targets:
                        if isinstance(t, ast.Name) and t.id == '__plugin__':
                            val = ast.literal_eval(node.value)
                            if isinstance(val, dict):
                                return val
        except Exception:
            continue
    return None

plugins = {}
# 目录型插件
for name in sorted(os.listdir(os.path.join(REPO_ROOT, 'plugins'))):
    full = os.path.join(REPO_ROOT, 'plugins', name)
    if os.path.isdir(full) and os.path.exists(os.path.join(full, '__init__.py')):
        meta = find_plugin_meta(full)
        if meta and meta.get('id'):
            pid = meta['id']
            plugins[pid] = {
                'name': meta.get('name', pid),
                'version': meta.get('version', '0.0.0'),
                'author': meta.get('author', ''),
                'description': meta.get('description', ''),
                'scope': meta.get('scope', 'user'),
                'path': f'plugins/{name}/',
                'icon': f'{BASE_URL}/plugins/icons/{name}_v2.svg',
            }
            if 'changelog' in meta:
                plugins[pid]['changelog'] = meta['changelog']
            if 'tags' in meta:
                plugins[pid]['tags'] = meta['tags']
    elif name.endswith('.py') and not name.startswith('_'):
        meta = find_plugin_meta(full)
        if meta and meta.get('id'):
            pid = meta['id']
            plugins[pid] = {
                'name': meta.get('name', pid),
                'version': meta.get('version', '0.0.0'),
                'author': meta.get('author', ''),
                'description': meta.get('description', ''),
                'scope': meta.get('scope', 'user'),
                'path': f'plugins/{name}',
            }
            if 'changelog' in meta:
                plugins[pid]['changelog'] = meta['changelog']
            if 'tags' in meta:
                plugins[pid]['tags'] = meta['tags']

# 仓库根单文件插件
for f in ['fz.py', 'ye_monitor.py']:
    full = os.path.join(REPO_ROOT, f)
    if os.path.exists(full):
        meta = find_plugin_meta(full)
        if meta and meta.get('id'):
            pid = meta['id']
            plugins[pid] = {
                'name': meta.get('name', pid),
                'version': meta.get('version', '0.0.0'),
                'author': meta.get('author', ''),
                'description': meta.get('description', ''),
                'scope': meta.get('scope', 'user'),
                'path': f,
            }
            if 'tags' in meta:
                plugins[pid]['tags'] = meta['tags']

manifest = {'plugins': dict(sorted(plugins.items()))}
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, ensure_ascii=False, indent=2)
    f.write('\n')

print(f'✅ 生成 {OUT}: {len(plugins)} 个插件\n')
for pid, info in sorted(plugins.items()):
    print(f"  {pid:<18} v{info['version']:<8} {info['path']}")