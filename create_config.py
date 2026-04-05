#!/usr/bin/env python3
import os
import json
from pathlib import Path

def create_default_config():
    """创建默认配置文件"""
    home = os.path.expanduser("~")
    config_dir = Path(home) / ".claude" / "plugins" / "memory" / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    config_file = config_dir / "config.json"

    default_config = {
        "enabled": True,
        "auto_start": True,
        "debug": False,
        "token_threshold": 25000,
        "score_threshold": 60.0,
        "max_injection_tokens": 0.2
    }

    if not config_file.exists():
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)
        print(f"创建默认配置文件: {config_file}")
    else:
        print(f"配置文件已存在: {config_file}")

    return config_file

if __name__ == "__main__":
    config_file = create_default_config()