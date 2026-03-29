"""自动导入 tools/ 下所有 .py 模块，触发 register_tool() 注册"""
import importlib
import pathlib

_dir = pathlib.Path(__file__).parent
for f in sorted(_dir.glob("*.py")):
    if f.name.startswith("_"):
        continue
    importlib.import_module(f".{f.stem}", package=__name__)
