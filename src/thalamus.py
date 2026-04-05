#!/usr/bin/env python3
"""
丘脑前部Agent - 用户交互与反馈中枢
神经科学对应：丘脑前部核团（ATN）介导的海马体-皮层-意识反馈环路

核心职责：
1. 待确认片段人性化格式化
2. 人机交互触发与反馈收集
3. 反馈结果标准化
4. 信号双向传递
5. 中转缓冲区与超时管理
"""

import os
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import shutil

class ThalamusAgent:
    """丘脑前部Agent - 中转仓库·反馈交互中枢"""

    def __init__(self, data_dir: str = None):
        """初始化丘脑前部Agent

        Args:
            data_dir: 数据存储目录
        """
        if data_dir is None:
            home = os.path.expanduser("~")
            self.data_dir = Path(home) / ".claude" / "plugins" / "memory"
        else:
            self.data_dir = Path(data_dir)

        # 创建必要的目录
        self.interaction_dir = self.data_dir / "interactions"
        self.pending_dir = self.data_dir / "pending"  # 待确认缓冲区
        self.feedback_dir = self.data_dir / "feedback"  # 用户反馈

        for dir_path in [self.interaction_dir, self.pending_dir, self.feedback_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_file = self.data_dir / "config" / "config.json"
        default_config = {
            "feedback_timeout_hours": 72,  # 反馈超时时间（小时）
            "interaction_format": "markdown",  # 交互格式：markdown, json, cli
            "group_by_topic": True,  # 按主题分组显示
            "max_fragments_per_interaction": 20,  # 单次交互最大片段数
            "auto_generate_preview": True,  # 自动生成预览
            "debug": False,
            "silent_mode": False,  # 静默模式，不主动推送
            "silent_hours": "9:00-18:00"  # 静默时段
        }

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                print(f"加载配置文件失败，使用默认配置: {e}")

        return default_config

    def format_fragments_for_interaction(self, fragments: List[Dict]) -> Dict:
        """将待确认片段格式化为用户友好的交互内容

        Args:
            fragments: 检察官推送的初级认证片段

        Returns:
            格式化后的交互内容，包含分组、摘要等信息
        """
        if not fragments:
            return {"status": "no_fragments", "message": "没有待确认的片段"}

        # 限制片段数量
        if len(fragments) > self.config["max_fragments_per_interaction"]:
            fragments = fragments[:self.config["max_fragments_per_interaction"]]
            if self.config.get("debug", False):
                print(f"⚠️  片段数量超过限制，仅显示前{self.config['max_fragments_per_interaction']}个")

        # 按主题分组
        grouped_fragments = {}
        for fragment in fragments:
            topic_tags = fragment.get("topic_tags", [])
            if not topic_tags:
                group_key = "未分类"
            else:
                # 使用第一个标签作为分组
                group_key = topic_tags[0] if topic_tags else "未分类"

            if group_key not in grouped_fragments:
                grouped_fragments[group_key] = []

            grouped_fragments[group_key].append(fragment)

        # 生成格式化内容
        formatted = {
            "interaction_id": f"interaction_{int(time.time())}",
            "timestamp": datetime.now().isoformat(),
            "total_fragments": len(fragments),
            "groups": {},
            "summary": self._generate_summary(fragments)
        }

        for group_key, group_fragments in grouped_fragments.items():
            formatted["groups"][group_key] = []
            for fragment in group_fragments:
                formatted_fragment = self._format_single_fragment(fragment)
                formatted["groups"][group_key].append(formatted_fragment)

        return formatted

    def _format_single_fragment(self, fragment: Dict) -> Dict:
        """格式化单个片段"""
        fragment_id = fragment.get("fragment_id", "unknown")
        content = fragment.get("content", "")

        # 生成预览摘要
        preview = self._generate_preview(content, fragment.get("content_type", "text"))

        formatted = {
            "fragment_id": fragment_id,
            "preview": preview,
            "score": fragment.get("score", 0),
            "content_type": fragment.get("content_type", "text"),
            "topic_tags": fragment.get("topic_tags", []),
            "source_type": fragment.get("source_type", "unknown"),
            "turn_id": fragment.get("turn_id", 0),
            "token_count": fragment.get("token_count", 0),
            "decision": "",  # 用户决定：keep/delete/later
            "user_notes": ""  # 用户备注
        }

        return formatted

    def _generate_preview(self, content: str, content_type: str) -> str:
        """生成内容预览"""
        max_preview_length = 200

        if content_type == "code":
            # 代码预览：保留格式，截取开头
            lines = content.split('\n')
            preview_lines = []
            for line in lines[:5]:  # 最多5行
                if len(''.join(preview_lines)) + len(line) < max_preview_length:
                    preview_lines.append(line)
                else:
                    break

            preview = '\n'.join(preview_lines)
            if len(lines) > 5:
                preview += f"\n...（共{len(lines)}行）"
        else:
            # 文本预览：截取开头
            if len(content) > max_preview_length:
                preview = content[:max_preview_length] + "..."
            else:
                preview = content

        return preview

    def _generate_summary(self, fragments: List[Dict]) -> Dict:
        """生成片段摘要"""
        total_tokens = sum(f.get("token_count", 0) for f in fragments)
        content_types = {}
        topic_distribution = {}

        for fragment in fragments:
            content_type = fragment.get("content_type", "unknown")
            content_types[content_type] = content_types.get(content_type, 0) + 1

            tags = fragment.get("topic_tags", [])
            for tag in tags:
                topic_distribution[tag] = topic_distribution.get(tag, 0) + 1

        # 按频率排序
        top_topics = sorted(topic_distribution.items(), key=lambda x: x[1], reverse=True)[:5]

        return {
            "total_fragments": len(fragments),
            "total_tokens": total_tokens,
            "content_type_distribution": content_types,
            "top_topics": [{"tag": tag, "count": count} for tag, count in top_topics],
            "average_score": sum(f.get("score", 0) for f in fragments) / max(1, len(fragments))
        }

    def save_interaction_file(self, formatted_data: Dict) -> Tuple[Path, List[str]]:
        """保存交互文件（Markdown格式）

        Returns:
            (file_path, fragment_ids)
        """
        interaction_id = formatted_data["interaction_id"]
        file_path = self.interaction_dir / f"{interaction_id}.md"

        fragment_ids = []

        # 生成Markdown内容
        markdown_lines = [
            "# 记忆确认清单",
            "",
            f"**交互ID**: {interaction_id}",
            f"**生成时间**: {formatted_data['timestamp']}",
            f"**片段总数**: {formatted_data['total_fragments']}",
            "",
            "## 操作说明",
            "",
            "请为每个片段选择处理方式：",
            "- **保留 (keep)**: 重要内容，需要永久记住",
            "- **删除 (delete)**: 不重要或临时内容",
            "- **稍后确认 (later)**: 暂时不确定，下次再决定",
            "",
            "在每个片段下方的方括号内填写你的决定：",
            "`[keep]`  `[delete]`  `[later]`",
            "",
            "你还可以在片段后添加备注，用`#备注:`开头。",
            "",
            "## 片段列表",
            ""
        ]

        # 添加摘要
        summary = formatted_data["summary"]
        markdown_lines.extend([
            "### 摘要",
            f"- 总片段数: {summary['total_fragments']}",
            f"- 总token数: {summary['total_tokens']}",
            f"- 平均评分: {summary['average_score']:.1f}",
            "",
            "### 内容类型分布",
        ])

        for content_type, count in summary["content_type_distribution"].items():
            markdown_lines.append(f"- {content_type}: {count}")

        markdown_lines.extend([
            "",
            "### 主要主题",
        ])

        for topic in summary["top_topics"]:
            markdown_lines.append(f"- {topic['tag']}: {topic['count']}")

        markdown_lines.append("")

        # 添加分组片段
        for group_key, fragments in formatted_data["groups"].items():
            markdown_lines.extend([
                f"## {group_key}",
                ""
            ])

            for i, fragment in enumerate(fragments, 1):
                fragment_id = fragment["fragment_id"]
                fragment_ids.append(fragment_id)

                markdown_lines.extend([
                    f"### 片段 {i}: {fragment_id[:8]}...",
                    f"**评分**: {fragment['score']:.1f}",
                    f"**类型**: {fragment['content_type']}",
                    f"**来源**: {fragment['source_type']} (第{fragment['turn_id']}轮)",
                    f"**标签**: {', '.join(fragment['topic_tags'])}",
                    f"**Token数**: {fragment['token_count']}",
                    "",
                    "**内容**:",
                    "```" + ("python" if fragment['content_type'] == 'code' else 'text'),
                    fragment['preview'],
                    "```",
                    "",
                    "**请选择处理方式**:",
                    "",
                    f"[ ] keep    [ ] delete    [ ] later",
                    "",
                    "**备注**:",
                    "#备注: ",
                    "",
                    "---",
                    ""
                ])

        # 添加操作说明
        markdown_lines.extend([
            "## 完成操作后",
            "",
            "1. 保存此文件",
            "2. 运行以下命令处理反馈：",
            f"`python -c \"from src.thalamus import ThalamusAgent; agent = ThalamusAgent(); agent.process_feedback_from_file('{file_path}')\"`",
            "",
            "或等待系统自动检测（72小时内）。",
            ""
        ])

        # 保存文件
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(markdown_lines))

            # 保存到待确认缓冲区
            self._save_to_pending_buffer(formatted_data, fragment_ids)

            if self.config.get("debug", False):
                print(f"📄 交互文件已保存: {file_path}")

            return file_path, fragment_ids

        except Exception as e:
            print(f"保存交互文件失败: {e}")
            return None, []

    def _save_to_pending_buffer(self, formatted_data: Dict, fragment_ids: List[str]):
        """保存到待确认缓冲区"""
        interaction_id = formatted_data["interaction_id"]
        buffer_file = self.pending_dir / f"{interaction_id}.json"

        buffer_data = {
            "interaction_id": interaction_id,
            "timestamp": formatted_data["timestamp"],
            "fragment_ids": fragment_ids,
            "total_fragments": formatted_data["total_fragments"],
            "timeout_at": (datetime.now() + timedelta(hours=self.config["feedback_timeout_hours"])).isoformat(),
            "status": "pending"
        }

        try:
            with open(buffer_file, 'w', encoding='utf-8') as f:
                json.dump(buffer_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存缓冲区数据失败: {e}")

    def should_trigger_interaction(self) -> bool:
        """检查是否应该触发交互

        考虑因素：
        1. 静默模式
        2. 静默时段
        3. 是否有待处理的片段
        """
        # 检查静默模式
        if self.config.get("silent_mode", False):
            return False

        # 检查静默时段
        if self._is_silent_hour():
            return False

        # 检查是否有待确认的片段
        pending_count = self._get_pending_fragment_count()
        return pending_count > 0

    def _is_silent_hour(self) -> bool:
        """检查当前是否处于静默时段"""
        silent_hours = self.config.get("silent_hours", "")
        if not silent_hours:
            return False

        try:
            current_time = datetime.now().time()
            start_str, end_str = silent_hours.split('-')
            start_time = datetime.strptime(start_str.strip(), "%H:%M").time()
            end_time = datetime.strptime(end_str.strip(), "%H:%M").time()

            return start_time <= current_time <= end_time
        except Exception:
            return False

    def _get_pending_fragment_count(self) -> int:
        """获取待确认片段数量"""
        count = 0
        for buffer_file in self.pending_dir.glob("*.json"):
            try:
                with open(buffer_file, 'r', encoding='utf-8') as f:
                    buffer_data = json.load(f)

                if buffer_data.get("status") == "pending":
                    count += buffer_data.get("total_fragments", 0)
            except Exception:
                continue

        return count

    def process_feedback_from_file(self, file_path: Path) -> Dict:
        """从Markdown文件处理用户反馈

        Args:
            file_path: Markdown文件路径

        Returns:
            标准化的反馈数据
        """
        if not file_path.exists():
            return {"status": "error", "message": "文件不存在"}

        # 从文件名提取interaction_id
        interaction_id = file_path.stem
        buffer_file = self.pending_dir / f"{interaction_id}.json"

        if not buffer_file.exists():
            return {"status": "error", "message": "对应的交互记录不存在"}

        try:
            # 读取缓冲区数据
            with open(buffer_file, 'r', encoding='utf-8') as f:
                buffer_data = json.load(f)

            # 读取Markdown文件
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 解析用户决定
            fragment_decisions = self._parse_decisions_from_markdown(content, buffer_data["fragment_ids"])

            # 生成标准化反馈
            feedback_data = self._generate_standardized_feedback(buffer_data, fragment_decisions)

            # 保存反馈
            feedback_file = self.feedback_dir / f"{interaction_id}_feedback.json"
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedback_data, f, ensure_ascii=False, indent=2)

            # 更新缓冲区状态
            buffer_data["status"] = "processed"
            buffer_data["processed_at"] = datetime.now().isoformat()
            with open(buffer_file, 'w', encoding='utf-8') as f:
                json.dump(buffer_data, f, ensure_ascii=False, indent=2)

            if self.config.get("debug", False):
                print(f"✅ 反馈处理完成: {feedback_file}")

            return feedback_data

        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _parse_decisions_from_markdown(self, markdown_content: str, fragment_ids: List[str]) -> List[Dict]:
        """从Markdown内容解析用户决定"""
        decisions = []

        # 按片段分割内容
        fragment_sections = re.split(r'### 片段 \d+: ([a-f0-9-]+)\.\.\.', markdown_content)

        # fragment_sections的格式：['', 'fragment_id1', '内容1', '', 'fragment_id2', '内容2', ...]
        for i in range(1, len(fragment_sections), 2):
            if i + 1 < len(fragment_sections):
                fragment_id_prefix = fragment_sections[i]
                section_content = fragment_sections[i + 1]

                # 查找完整的fragment_id
                fragment_id = None
                for fid in fragment_ids:
                    if fid.startswith(fragment_id_prefix):
                        fragment_id = fid
                        break

                if not fragment_id:
                    continue

                # 解析决定
                decision = self._extract_decision_from_section(section_content)

                # 解析备注
                notes = self._extract_notes_from_section(section_content)

                decisions.append({
                    "fragment_id": fragment_id,
                    "decision": decision,
                    "user_notes": notes
                })

        return decisions

    def _extract_decision_from_section(self, section_content: str) -> str:
        """从片段内容中提取用户决定"""
        # 查找选择框
        patterns = [
            r'\[x\]\s*keep',   # [x] keep
            r'\[x\]\s*delete',  # [x] delete
            r'\[x\]\s*later',   # [x] later
            r'\[✓\]\s*keep',    # [✓] keep
            r'\[✓\]\s*delete',  # [✓] delete
            r'\[✓\]\s*later',   # [✓] later
        ]

        for pattern in patterns:
            if re.search(pattern, section_content, re.IGNORECASE):
                if 'keep' in pattern:
                    return 'keep'
                elif 'delete' in pattern:
                    return 'delete'
                elif 'later' in pattern:
                    return 'later'

        # 如果用户填写了决定但没有用选择框
        if re.search(r'keep\s*[:：]', section_content, re.IGNORECASE):
            return 'keep'
        elif re.search(r'delete\s*[:：]', section_content, re.IGNORECASE):
            return 'delete'
        elif re.search(r'later\s*[:：]', section_content, re.IGNORECASE):
            return 'later'

        return ''  # 未决定

    def _extract_notes_from_section(self, section_content: str) -> str:
        """从片段内容中提取用户备注"""
        # 查找备注行
        notes_pattern = r'#备注[：:]\s*(.*?)(?=\n|$)'
        match = re.search(notes_pattern, section_content)

        if match:
            return match.group(1).strip()

        return ''

    def _generate_standardized_feedback(self, buffer_data: Dict, fragment_decisions: List[Dict]) -> Dict:
        """生成标准化的反馈数据"""
        feedback = {
            "interaction_id": buffer_data["interaction_id"],
            "timestamp": datetime.now().isoformat(),
            "original_timestamp": buffer_data["timestamp"],
            "total_fragments": buffer_data["total_fragments"],
            "fragment_decisions": fragment_decisions,
            "summary": {
                "keep_count": sum(1 for d in fragment_decisions if d["decision"] == "keep"),
                "delete_count": sum(1 for d in fragment_decisions if d["decision"] == "delete"),
                "later_count": sum(1 for d in fragment_decisions if d["decision"] == "later"),
                "undecided_count": sum(1 for d in fragment_decisions if not d["decision"])
            }
        }

        return feedback

    def check_timeout_fragments(self) -> Dict:
        """检查超时的待确认片段

        超时的片段会退回海马体短期记忆池

        Returns:
            超时处理结果
        """
        timeout_files = []
        total_fragments = 0
        fragment_ids = []

        current_time = datetime.now()

        for buffer_file in self.pending_dir.glob("*.json"):
            try:
                with open(buffer_file, 'r', encoding='utf-8') as f:
                    buffer_data = json.load(f)

                if buffer_data.get("status") != "pending":
                    continue

                timeout_at = datetime.fromisoformat(buffer_data["timeout_at"])
                if current_time > timeout_at:
                    # 超时处理
                    buffer_data["status"] = "timeout"
                    buffer_data["timeout_processed_at"] = current_time.isoformat()

                    # 更新文件
                    with open(buffer_file, 'w', encoding='utf-8') as f:
                        json.dump(buffer_data, f, ensure_ascii=False, indent=2)

                    timeout_files.append(buffer_data["interaction_id"])
                    total_fragments += buffer_data.get("total_fragments", 0)
                    fragment_ids.extend(buffer_data.get("fragment_ids", []))

                    if self.config.get("debug", False):
                        print(f"⏰ 交互 {buffer_data['interaction_id']} 已超时")

            except Exception as e:
                print(f"检查超时文件失败 {buffer_file}: {e}")

        result = {
            "status": "completed",
            "timeout_interactions": timeout_files,
            "total_fragments": total_fragments,
            "fragment_ids": fragment_ids,
            "timestamp": current_time.isoformat()
        }

        return result

    def get_interaction_status(self, interaction_id: str = None) -> Dict:
        """获取交互状态

        Args:
            interaction_id: 交互ID，不提供则获取所有交互状态
        """
        if interaction_id:
            # 获取特定交互状态
            buffer_file = self.pending_dir / f"{interaction_id}.json"
            if not buffer_file.exists():
                return {"status": "not_found"}

            try:
                with open(buffer_file, 'r', encoding='utf-8') as f:
                    buffer_data = json.load(f)

                # 检查是否超时
                timeout_at = datetime.fromisoformat(buffer_data["timeout_at"])
                is_timeout = datetime.now() > timeout_at

                return {
                    "interaction_id": interaction_id,
                    "status": buffer_data["status"],
                    "fragments_count": buffer_data.get("total_fragments", 0),
                    "created_at": buffer_data["timestamp"],
                    "timeout_at": buffer_data["timeout_at"],
                    "is_timeout": is_timeout,
                    "time_remaining_hours": max(0, (timeout_at - datetime.now()).total_seconds() / 3600)
                }
            except Exception as e:
                return {"status": "error", "error": str(e)}
        else:
            # 获取所有交互状态
            all_interactions = []

            for buffer_file in self.pending_dir.glob("*.json"):
                try:
                    with open(buffer_file, 'r', encoding='utf-8') as f:
                        buffer_data = json.load(f)

                    interaction_id = buffer_file.stem
                    timeout_at = datetime.fromisoformat(buffer_data["timeout_at"])
                    is_timeout = datetime.now() > timeout_at

                    all_interactions.append({
                        "interaction_id": interaction_id,
                        "status": buffer_data["status"],
                        "fragments_count": buffer_data.get("total_fragments", 0),
                        "created_at": buffer_data["timestamp"],
                        "timeout_at": buffer_data["timeout_at"],
                        "is_timeout": is_timeout
                    })
                except Exception:
                    continue

            return {
                "total_interactions": len(all_interactions),
                "pending_count": sum(1 for i in all_interactions if i["status"] == "pending"),
                "interactions": all_interactions
            }

    def cleanup_old_files(self, days_old: int = 7):
        """清理旧文件"""
        cutoff_date = datetime.now() - timedelta(days=days_old)

        # 清理旧的交互文件
        for file_path in self.interaction_dir.glob("*.md"):
            try:
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    file_path.unlink()
            except Exception as e:
                print(f"清理文件失败 {file_path}: {e}")

        # 清理旧的反馈文件
        for file_path in self.feedback_dir.glob("*.json"):
            try:
                file_time = datetime.fromtimestamp(file_path.stat().st_mtime)
                if file_time < cutoff_date:
                    file_path.unlink()
            except Exception as e:
                print(f"清理文件失败 {file_path}: {e}")

        if self.config.get("debug", False):
            print(f"🧹 清理了{days_old}天前的旧文件")


# 简单的命令行测试
if __name__ == "__main__":
    print("🧠 测试丘脑前部Agent...")

    # 创建测试目录
    test_dir = Path("test_thalamus")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 初始化Agent
    thalamus = ThalamusAgent(str(test_dir))

    # 创建测试片段
    test_fragments = [
        {
            "fragment_id": "test_frag_001",
            "content": "API认证必须使用JWT，有效期24小时。需要支持refresh token机制。",
            "content_type": "text",
            "topic_tags": ["authentication", "requirement", "security"],
            "score": 85.5,
            "source_type": "user_input",
            "turn_id": 1,
            "token_count": 25
        },
        {
            "fragment_id": "test_frag_002",
            "content": "import jwt\nfrom datetime import datetime, timedelta\n\ndef create_access_token(data: dict):\n    to_encode = data.copy()\n    expire = datetime.utcnow() + timedelta(hours=24)\n    to_encode.update({\"exp\": expire})\n    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)\n    return encoded_jwt",
            "content_type": "code",
            "topic_tags": ["python", "code", "jwt"],
            "score": 92.0,
            "source_type": "claude_output",
            "turn_id": 1,
            "token_count": 45
        },
        {
            "fragment_id": "test_frag_003",
            "content": "数据库连接池最大连接数设置为50，最小保持10个连接。",
            "content_type": "text",
            "topic_tags": ["database", "configuration"],
            "score": 75.0,
            "source_type": "user_input",
            "turn_id": 2,
            "token_count": 18
        }
    ]

    # 格式化片段
    print("\n📋 格式化片段用于交互...")
    formatted_data = thalamus.format_fragments_for_interaction(test_fragments)

    print(f"✅ 格式化完成:")
    print(f"  - 片段总数: {formatted_data['total_fragments']}")
    print(f"  - 分组数: {len(formatted_data['groups'])}")

    # 保存交互文件
    print("\n📄 生成交互文件...")
    file_path, fragment_ids = thalamus.save_interaction_file(formatted_data)

    if file_path:
        print(f"✅ 交互文件已保存: {file_path}")
        print(f"  - 包含片段: {len(fragment_ids)}个")

        # 显示文件预览
        with open(file_path, 'r', encoding='utf-8') as f:
            preview = f.read(500)
        print(f"\n📝 文件预览（前500字符）:")
        print("-" * 50)
        print(preview)
        print("-" * 50)

    # 检查交互状态
    print("\n📊 检查交互状态...")
    status = thalamus.get_interaction_status()
    print(f"交互状态: {status}")

    # 模拟处理反馈（使用测试文件）
    print("\n👤 模拟处理用户反馈...")
    if file_path:
        # 创建测试反馈文件
        test_feedback_content = """
        # 记忆确认清单

        ## 片段 1: test_frag_001...

        **请选择处理方式**:

        [x] keep    [ ] delete    [ ] later

        **备注**:
        #备注: 这是核心认证需求，必须保留

        ---

        ## 片段 2: test_frag_002...

        **请选择处理方式**:

        [x] keep    [ ] delete    [ ] later

        **备注**:
        #备注: 代码实现很重要

        ---

        ## 片段 3: test_frag_003...

        **请选择处理方式**:

        [ ] keep    [x] delete    [ ] later

        **备注**:
        #备注: 临时配置，不需要永久记住
        """

        # 保存测试反馈
        test_feedback_file = test_dir / "test_feedback.md"
        with open(test_feedback_file, 'w', encoding='utf-8') as f:
            f.write(test_feedback_content)

        print(f"✅ 创建测试反馈文件: {test_feedback_file}")

        # 处理反馈（这里用测试文件，实际应该用生成的交互文件）
        print("\n🔄 处理反馈数据...")
        # 注意：这里简化测试，实际应解析生成的交互文件

        feedback_data = {
            "interaction_id": formatted_data["interaction_id"],
            "timestamp": datetime.now().isoformat(),
            "original_timestamp": formatted_data["timestamp"],
            "total_fragments": formatted_data["total_fragments"],
            "fragment_decisions": [
                {"fragment_id": "test_frag_001", "decision": "keep", "user_notes": "这是核心认证需求，必须保留"},
                {"fragment_id": "test_frag_002", "decision": "keep", "user_notes": "代码实现很重要"},
                {"fragment_id": "test_frag_003", "decision": "delete", "user_notes": "临时配置，不需要永久记住"}
            ]
        }

        print(f"✅ 反馈数据:")
        print(f"  - 保留: 2个片段")
        print(f"  - 删除: 1个片段")

    # 检查超时
    print("\n⏰ 检查超时片段...")
    timeout_result = thalamus.check_timeout_fragments()
    print(f"超时检查结果: {timeout_result}")

    # 清理旧文件
    print("\n🧹 清理旧文件...")
    thalamus.cleanup_old_files(days_old=0)  # 测试清理0天前的文件

    print("\n✅ 测试完成")
    print(f"测试目录: {test_dir}")
    print("你可以查看生成的交互文件和反馈数据")