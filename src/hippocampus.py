#!/usr/bin/env python3
"""
海马体Agent - 对话记录与语义分割
神经科学对应：海马体CA1/CA3区情景记忆编码神经元

核心职责：
1. 实时记录完整对话单元（用户输入 + Claude输出）
2. 基础时序剪辑与语义分割
3. 短期记忆池管理
4. Token计数与阈值触发
5. 记忆片段标准化处理
"""

import os
import json
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

class HippocampusAgent:
    """海马体临时仓库·时序剪辑师"""

    def __init__(self, data_dir: str = None):
        """初始化海马体Agent

        Args:
            data_dir: 数据存储目录，默认 ~/.claude/plugins/memory
        """
        if data_dir is None:
            home = os.path.expanduser("~")
            self.data_dir = Path(home) / ".claude" / "plugins" / "memory"
        else:
            self.data_dir = Path(data_dir)

        # 创建必要的目录
        self.short_term_dir = self.data_dir / "short-term"
        self.sessions_dir = self.data_dir / "sessions"
        self.config_dir = self.data_dir / "config"

        for dir_path in [self.short_term_dir, self.sessions_dir, self.config_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

        # 状态变量
        self.current_session_id = None
        self.current_turn_id = 0
        self.total_tokens = 0
        self.short_term_fragments = []  # 短期记忆片段池

    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_file = self.config_dir / "config.json"
        default_config = {
            "token_threshold": 25000,  # 默认触发阈值
            "warning_threshold": 20000,  # 预警阈值（80%）
            "min_fragment_tokens": 128,
            "max_fragment_tokens": 1024,
            "short_term_retention_days": 7,
            "debug": False
        }

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                print(f"加载配置文件失败，使用默认配置: {e}")

        return default_config

    def start_new_session(self, session_id: str = None) -> str:
        """开始新的对话会话

        Args:
            session_id: 可选的自定义会话ID，默认生成UUID

        Returns:
            会话ID
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        self.current_session_id = session_id
        self.current_turn_id = 0
        self.total_tokens = 0
        self.short_term_fragments = []

        # 创建会话文件
        session_file = self.sessions_dir / f"{session_id}.json"
        session_data = {
            "session_id": session_id,
            "start_time": datetime.now().isoformat(),
            "total_tokens": 0,
            "total_turns": 0,
            "status": "active"
        }

        with open(session_file, 'w', encoding='utf-8') as f:
            json.dump(session_data, f, ensure_ascii=False, indent=2)

        if self.config.get("debug", False):
            print(f"✅ 开始新会话: {session_id}")

        return session_id

    def record_turn(self, user_input: str, claude_output: str) -> Dict:
        """记录单轮对话

        Args:
            user_input: 用户输入内容
            claude_output: Claude输出内容

        Returns:
            记录结果，包含token统计和片段信息
        """
        if self.current_session_id is None:
            self.start_new_session()

        self.current_turn_id += 1

        # 估算token（简化版本）
        user_tokens = self._estimate_tokens(user_input)
        claude_tokens = self._estimate_tokens(claude_output)
        turn_tokens = user_tokens + claude_tokens
        self.total_tokens += turn_tokens

        # 创建对话单元
        turn_data = {
            "turn_id": self.current_turn_id,
            "user_input": user_input,
            "claude_output": claude_output,
            "user_tokens": user_tokens,
            "claude_tokens": claude_tokens,
            "total_tokens": turn_tokens,
            "timestamp": datetime.now().isoformat()
        }

        # 语义分割为记忆片段
        fragments = self._segment_to_fragments(turn_data)
        self.short_term_fragments.extend(fragments)

        # 保存到会话文件
        self._save_turn_to_session(turn_data, fragments)

        # 检查是否需要触发记忆巩固
        threshold_check = self._check_token_threshold()

        result = {
            "session_id": self.current_session_id,
            "turn_id": self.current_turn_id,
            "turn_tokens": turn_tokens,
            "total_tokens": self.total_tokens,
            "fragments_count": len(fragments),
            "should_consolidate": threshold_check["should_consolidate"],
            "threshold_warning": threshold_check["threshold_warning"]
        }

        if self.config.get("debug", False):
            print(f"📝 记录第{self.current_turn_id}轮对话: {turn_tokens} tokens")
            if threshold_check["threshold_warning"]:
                print(f"⚠️  接近阈值: {self.total_tokens}/{self.config['token_threshold']}")

        return result

    def _estimate_tokens(self, text: str) -> int:
        """估算文本的token数量（简化版本）

        Note: 生产环境应使用与Claude一致的tokenizer
        这里使用近似估算：1 token ≈ 4个英文字符 或 2个中文字符
        """
        if not text:
            return 0

        # 中文字符计数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', text))

        # 其他字符计数
        other_chars = len(text) - chinese_chars

        # 估算token：中文2字符=1token，英文4字符=1token
        tokens = chinese_chars / 2 + other_chars / 4

        return max(1, int(tokens))

    def _segment_to_fragments(self, turn_data: Dict) -> List[Dict]:
        """将对话单元分割为记忆片段

        简化版本：基于标点、代码块和主题进行分割
        """
        fragments = []
        turn_id = turn_data["turn_id"]

        # 处理用户输入
        user_fragments = self._split_text_to_fragments(
            turn_data["user_input"],
            "user_input",
            turn_id
        )
        fragments.extend(user_fragments)

        # 处理Claude输出
        claude_fragments = self._split_text_to_fragments(
            turn_data["claude_output"],
            "claude_output",
            turn_id
        )
        fragments.extend(claude_fragments)

        return fragments

    def _split_text_to_fragments(self, text: str, source_type: str, turn_id: int) -> List[Dict]:
        """将文本分割为片段

        分割策略：
        1. 按代码块分割（```code```）
        2. 按段落分割（\n\n）
        3. 按句子分割（。！？）
        4. 确保片段在最小/最大token范围内
        """
        if not text.strip():
            return []

        fragments = []

        # 首先按代码块分割
        code_pattern = r'```[\s\S]*?```'
        code_blocks = list(re.finditer(code_pattern, text))

        if code_blocks:
            last_end = 0
            for match in code_blocks:
                # 处理代码块之前的文本
                before_code = text[last_end:match.start()]
                if before_code.strip():
                    text_fragments = self._split_by_sentences(before_code)
                    for frag_text in text_fragments:
                        fragments.append(self._create_fragment(
                            frag_text, source_type, turn_id, "text"
                        ))

                # 处理代码块
                code_text = match.group()
                fragments.append(self._create_fragment(
                    code_text, source_type, turn_id, "code"
                ))

                last_end = match.end()

            # 处理最后一个代码块之后的文本
            after_code = text[last_end:]
            if after_code.strip():
                text_fragments = self._split_by_sentences(after_code)
                for frag_text in text_fragments:
                    fragments.append(self._create_fragment(
                        frag_text, source_type, turn_id, "text"
                    ))
        else:
            # 没有代码块，直接按句子分割
            text_fragments = self._split_by_sentences(text)
            for frag_text in text_fragments:
                fragments.append(self._create_fragment(
                    frag_text, source_type, turn_id, "text"
                ))

        # 合并过小的片段
        merged_fragments = self._merge_small_fragments(fragments)

        return merged_fragments

    def _split_by_sentences(self, text: str) -> List[str]:
        """按句子分割文本"""
        # 按换行符分割段落
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]

        sentences = []
        for para in paragraphs:
            # 按中文句子分割
            para_sentences = re.split(r'([。！？])', para)

            # 重组句子
            current_sentence = ""
            for i in range(0, len(para_sentences), 2):
                if i < len(para_sentences):
                    current_sentence += para_sentences[i]
                    if i + 1 < len(para_sentences):
                        current_sentence += para_sentences[i + 1]

                    if current_sentence.strip():
                        sentences.append(current_sentence.strip())
                        current_sentence = ""

        return sentences

    def _create_fragment(self, content: str, source_type: str, turn_id: int, content_type: str) -> Dict:
        """创建标准化的记忆片段"""
        fragment_id = str(uuid.uuid4())
        token_count = self._estimate_tokens(content)

        # 提取主题标签（简化版本）
        topic_tags = self._extract_topic_tags(content, content_type)

        fragment = {
            "fragment_id": fragment_id,
            "session_id": self.current_session_id,
            "turn_id": turn_id,
            "timestamp": datetime.now().isoformat(),
            "content": content,
            "token_count": token_count,
            "source_type": source_type,  # "user_input" 或 "claude_output"
            "content_type": content_type,  # "text" 或 "code"
            "topic_tags": topic_tags,
            "code_related": content_type == "code",
            "score": 0,  # 初始分数，由检察官Agent设置
            "auth_status": "unprocessed",
            "version": "1.0",
            "expired": False
        }

        return fragment

    def _extract_topic_tags(self, content: str, content_type: str) -> List[str]:
        """从内容中提取主题标签"""
        tags = []

        if content_type == "code":
            # 代码相关标签
            code_keywords = {
                "python": ["def ", "import ", "class ", "print("],
                "javascript": ["function ", "const ", "let ", "console."],
                "java": ["public ", "class ", "void ", "System.out."],
                "html": ["<div", "<p", "<span", "class="],
                "css": ["{", "}", ".", "#", "@"]
            }

            for lang, patterns in code_keywords.items():
                for pattern in patterns:
                    if pattern in content.lower():
                        tags.append(lang)
                        break

            tags.append("code")

        else:
            # 文本内容标签
            text_lower = content.lower()

            # 需求相关关键词
            requirement_keywords = ["需求", "要求", "必须", "需要", "要", "should", "must", "require"]
            for keyword in requirement_keywords:
                if keyword in text_lower:
                    tags.append("requirement")
                    break

            # 约束相关关键词
            constraint_keywords = ["不能", "禁止", "不要", "避免", "cannot", "must not", "avoid"]
            for keyword in constraint_keywords:
                if keyword in text_lower:
                    tags.append("constraint")
                    break

            # 技术相关关键词
            tech_keywords = ["api", "数据库", "框架", "算法", "性能", "bug", "错误"]
            for keyword in tech_keywords:
                if keyword in text_lower:
                    tags.append("technical")
                    break

        # 添加通用标签
        if "?" in content:
            tags.append("question")
        if "!" in content:
            tags.append("emphasis")

        return list(set(tags))  # 去重

    def _merge_small_fragments(self, fragments: List[Dict]) -> List[Dict]:
        """合并过小的记忆片段"""
        if not fragments:
            return []

        merged = []
        current_fragment = fragments[0].copy()

        for fragment in fragments[1:]:
            # 如果当前片段很小，且下一个片段也小，且主题相似，则合并
            if (current_fragment["token_count"] < self.config["min_fragment_tokens"] and
                fragment["token_count"] < self.config["min_fragment_tokens"] and
                self._fragments_similar(current_fragment, fragment)):

                # 合并内容
                current_fragment["content"] += "\n\n" + fragment["content"]
                current_fragment["token_count"] += fragment["token_count"]
                # 合并标签
                current_fragment["topic_tags"] = list(set(
                    current_fragment["topic_tags"] + fragment["topic_tags"]
                ))
            else:
                merged.append(current_fragment)
                current_fragment = fragment.copy()

        merged.append(current_fragment)

        # 分割过大的片段
        final_fragments = []
        for fragment in merged:
            if fragment["token_count"] > self.config["max_fragment_tokens"]:
                split_fragments = self._split_large_fragment(fragment)
                final_fragments.extend(split_fragments)
            else:
                final_fragments.append(fragment)

        return final_fragments

    def _fragments_similar(self, frag1: Dict, frag2: Dict) -> bool:
        """判断两个片段是否相似（简化版本）"""
        # 如果都是代码或都是文本
        if frag1["content_type"] != frag2["content_type"]:
            return False

        # 如果主题标签有重叠
        common_tags = set(frag1["topic_tags"]) & set(frag2["topic_tags"])
        return len(common_tags) > 0

    def _split_large_fragment(self, fragment: Dict) -> List[Dict]:
        """分割过大的记忆片段"""
        content = fragment["content"]
        max_tokens = self.config["max_fragment_tokens"]

        if fragment["content_type"] == "code":
            # 代码按空行分割
            parts = re.split(r'\n\s*\n', content)
        else:
            # 文本按句子分割
            parts = self._split_by_sentences(content)

        split_fragments = []
        current_part = ""
        current_tokens = 0

        for part in parts:
            part_tokens = self._estimate_tokens(part)

            if current_tokens + part_tokens <= max_tokens:
                current_part += ("\n\n" if current_part else "") + part
                current_tokens += part_tokens
            else:
                if current_part:
                    new_fragment = fragment.copy()
                    new_fragment["content"] = current_part
                    new_fragment["token_count"] = current_tokens
                    new_fragment["fragment_id"] = str(uuid.uuid4())
                    split_fragments.append(new_fragment)

                current_part = part
                current_tokens = part_tokens

        # 添加最后一个部分
        if current_part:
            new_fragment = fragment.copy()
            new_fragment["content"] = current_part
            new_fragment["token_count"] = current_tokens
            new_fragment["fragment_id"] = str(uuid.uuid4())
            split_fragments.append(new_fragment)

        return split_fragments

    def _save_turn_to_session(self, turn_data: Dict, fragments: List[Dict]):
        """保存对话轮次到会话文件"""
        session_file = self.sessions_dir / f"{self.current_session_id}.json"

        if not session_file.exists():
            return

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            # 更新会话数据
            session_data["total_tokens"] = self.total_tokens
            session_data["total_turns"] = self.current_turn_id
            session_data["last_update"] = datetime.now().isoformat()

            # 保存片段到短期记忆池
            self._save_to_short_term_pool(fragments)

            # 更新会话文件
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"保存会话数据失败: {e}")

    def _save_to_short_term_pool(self, fragments: List[Dict]):
        """保存片段到短期记忆池"""
        for fragment in fragments:
            fragment_file = self.short_term_dir / f"{fragment['fragment_id']}.json"

            try:
                with open(fragment_file, 'w', encoding='utf-8') as f:
                    json.dump(fragment, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存片段失败: {e}")

    def _check_token_threshold(self) -> Dict:
        """检查token阈值"""
        token_threshold = self.config["token_threshold"]
        warning_threshold = self.config["warning_threshold"]

        result = {
            "should_consolidate": False,
            "threshold_warning": False,
            "current_tokens": self.total_tokens,
            "threshold": token_threshold
        }

        if self.total_tokens >= token_threshold:
            result["should_consolidate"] = True

        if self.total_tokens >= warning_threshold:
            result["threshold_warning"] = True

        return result

    def get_short_term_fragments(self) -> List[Dict]:
        """获取短期记忆池中的所有片段"""
        fragments = []

        for fragment_file in self.short_term_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                # 只返回未处理的片段
                if fragment.get("auth_status") == "unprocessed":
                    fragments.append(fragment)

            except Exception as e:
                print(f"读取片段文件失败 {fragment_file}: {e}")

        return fragments

    def clear_processed_fragments(self, fragment_ids: List[str]):
        """清理已处理的片段"""
        for fragment_id in fragment_ids:
            fragment_file = self.short_term_dir / f"{fragment_id}.json"
            if fragment_file.exists():
                try:
                    # 移动到归档目录而不是直接删除
                    archive_dir = self.short_term_dir / "archive"
                    archive_dir.mkdir(exist_ok=True)
                    fragment_file.rename(archive_dir / f"{fragment_id}.json")
                except Exception as e:
                    print(f"移动片段文件失败 {fragment_id}: {e}")

    def get_session_info(self) -> Dict:
        """获取当前会话信息"""
        if self.current_session_id is None:
            return {"status": "no_active_session"}

        session_file = self.sessions_dir / f"{self.current_session_id}.json"
        if not session_file.exists():
            return {"status": "session_not_found"}

        try:
            with open(session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            return {
                "session_id": self.current_session_id,
                "total_tokens": self.total_tokens,
                "total_turns": self.current_turn_id,
                "fragments_in_pool": len(self.get_short_term_fragments()),
                "start_time": session_data.get("start_time"),
                "status": session_data.get("status", "active")
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def end_session(self):
        """结束当前会话"""
        if self.current_session_id is None:
            return

        session_file = self.sessions_dir / f"{self.current_session_id}.json"
        if session_file.exists():
            try:
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

                session_data["status"] = "completed"
                session_data["end_time"] = datetime.now().isoformat()

                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)

            except Exception as e:
                print(f"结束会话失败: {e}")

        # 重置状态
        self.current_session_id = None
        self.current_turn_id = 0
        self.total_tokens = 0
        self.short_term_fragments = []


# 简单的命令行测试
if __name__ == "__main__":
    print("🧠 测试海马体Agent...")

    # 创建测试目录
    test_dir = Path("test_hippocampus")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 初始化Agent
    hippocampus = HippocampusAgent(str(test_dir))

    # 开始新会话
    session_id = hippocampus.start_new_session()
    print(f"📂 会话ID: {session_id}")

    # 测试记录对话
    test_inputs = [
        ("我需要开发一个Python API服务器，使用FastAPI框架",
         "好的，我可以帮你设计一个FastAPI服务器。首先需要安装依赖：pip install fastapi uvicorn"),
        ("数据库要用PostgreSQL，需要连接池管理",
         "可以使用asyncpg作为PostgreSQL驱动，并配置连接池。需要安装：pip install asyncpg"),
        ("API需要认证，使用JWT token",
         "好的，我会添加JWT认证中间件。需要安装：pip install python-jose[cryptography]")
    ]

    for i, (user_input, claude_output) in enumerate(test_inputs):
        result = hippocampus.record_turn(user_input, claude_output)
        print(f"📝 第{result['turn_id']}轮: {result['turn_tokens']} tokens, 总计: {result['total_tokens']}")

    # 获取会话信息
    session_info = hippocampus.get_session_info()
    print(f"\n📊 会话信息: {session_info}")

    # 获取短期记忆片段
    fragments = hippocampus.get_short_term_fragments()
    print(f"\n📋 短期记忆片段数: {len(fragments)}")
    for i, fragment in enumerate(fragments[:3]):  # 显示前3个片段
        print(f"  {i+1}. {fragment['content'][:50]}... (tags: {fragment['topic_tags']})")

    # 清理
    hippocampus.end_session()
    print("\n✅ 测试完成")
    # 保留测试目录供检查