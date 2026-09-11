#!/usr/bin/env python3
"""my115: 批量把 ctx.log.info/warning 替换为 _log(ctx, level, ...), error 保留 ctx.log.error"""
import re

PATH = '/root/AWBotNest-Plugins/plugins/my115/__init__.py'
src = open(PATH, encoding='utf-8').read()

# info → _log(ctx, "info", ...
src = re.sub(r'ctx\.log\.info\(', '_log(ctx, "info", ', src)
# warning → _log(ctx, "warning", ...  (warning 也不刷平台日志, 只进插件日志)
src = re.sub(r'ctx\.log\.warning\(', '_log(ctx, "warning", ', src)
# error 保留 ctx.log.error — 但已有 _log(...,"error") 内处理, 原来的不重复

open(PATH, 'w', encoding='utf-8').write(src)
print('替换完成')

# 验证
import ast
ast.parse(src)
print('语法 OK ✅')
print('剩余 ctx.log.error:', src.count('ctx.log.error('))
print('_log 调用数:', src.count('_log(ctx, '))