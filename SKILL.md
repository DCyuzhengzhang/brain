---
name: memory-management
description: Use when working on long conversations with Claude Code to prevent forgetting key information, requirements, or constraints across multiple dialogue turns.
---

# 四Agent记忆管理系统

## 概述
基于人脑记忆机制的四Agent协同系统，解决长对话场景下关键信息遗忘问题，模拟海马体临时存储、组蛋白甲基转移酶认证、丘脑前部反馈、大脑皮层永久存储的全链路记忆巩固。

## 核心架构
四个Agent对应人脑记忆环路，各司其职：

1. **海马体Agent**：对话记录与语义分割
2. **组蛋白甲基转移酶Agent**：记忆价值筛选与认证
3. **丘脑前部Agent**：用户反馈收集
4. **大脑皮层Agent**：永久存储与召回

## 工作流程
1. 每轮对话被海马体记录并分割为记忆片段
2. 累计token达到阈值（默认25k）触发记忆巩固
3. 检察官初筛片段，推送给用户确认
4. 用户反馈后，检察官二次认证
5. 认证通过的片段写入永久记忆库
6. 后续对话自动注入相关记忆

## 如何使用
插件自动运行，无需手动配置。当对话达到阈值时，会自动弹出记忆确认界面。

### 主要功能
- 自动对话记录与语义分割
- Token阈值触发记忆巩固（可配置）
- 用户交互式记忆确认
- 永久记忆存储与智能召回
- 本地文件存储，无需外部依赖

### 配置文件
```
~/.claude/plugins/memory/config.json
```

### 数据目录
```
~/.claude/plugins/memory/data/
  |- short-term/    # 短期记忆池
  |- long-term/     # 永久记忆库
  |- sessions/      # 会话历史
```

## 强制约束
1. 永不篡改对话原始语义
2. 永不绕过用户确认写入永久记忆
3. 永不突破上下文token物理上限
4. 永不泄露用户数据至第三方
5. 永不干扰Claude Code原生功能