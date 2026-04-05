#!/usr/bin/env python3
"""
大脑皮层Agent - 永久记忆存储与召回
神经科学对应：大脑皮层分布式永久记忆印记系统

核心职责：
1. 永久记忆合规写入（仅接收最终认证片段）
2. 记忆索引与知识库构建（关键词+标签检索）
3. 上下文智能注入（基于用户输入召回相关记忆）
4. 记忆版本迭代管理（标记过期内容）
5. 记忆库生命周期管理（导出、导入、备份）
"""

import os
import json
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
import hashlib
import shutil

class CortexAgent:
    """大脑皮层Agent - 永久仓库·长期记忆管理者"""

    def __init__(self, data_dir: str = None):
        """初始化大脑皮层Agent

        Args:
            data_dir: 数据存储目录
        """
        if data_dir is None:
            home = os.path.expanduser("~")
            self.data_dir = Path(home) / ".claude" / "plugins" / "memory"
        else:
            self.data_dir = Path(data_dir)

        # 创建必要的目录
        self.long_term_dir = self.data_dir / "long-term"
        self.index_dir = self.data_dir / "index"
        self.backup_dir = self.data_dir / "backup"
        self.export_dir = self.data_dir / "export"

        for dir_path in [self.long_term_dir, self.index_dir, self.backup_dir, self.export_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

        # 内存索引
        self.keyword_index = {}  # 关键词 -> 片段ID列表
        self.tag_index = {}  # 标签 -> 片段ID列表
        self.topic_index = {}  # 主题 -> 片段ID列表
        self.session_index = {}  # 会话ID -> 片段ID列表

        # 加载索引
        self._load_indices()

    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_file = self.data_dir / "config" / "config.json"
        default_config = {
            "max_injection_tokens": 0.2,  # 注入token不超过剩余上下文的20%
            "max_fragments_per_query": 5,  # 单次查询最多召回片段数
            "similarity_threshold": 0.3,  # 相似度阈值
            "version_management": True,  # 启用版本管理
            "backup_frequency_days": 1,  # 备份频率（天）
            "debug": False,
            "index_update_frequency": "immediate",  # 索引更新频率：immediate, daily, weekly
            "keyword_extraction": "basic",  # 关键词提取：basic, tfidf
            "enable_fuzzy_match": True  # 启用模糊匹配
        }

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                print(f"加载配置文件失败，使用默认配置: {e}")

        return default_config

    def _load_indices(self):
        """从磁盘加载索引"""
        index_file = self.index_dir / "indices.json"
        if index_file.exists():
            try:
                with open(index_file, 'r', encoding='utf-8') as f:
                    indices = json.load(f)

                self.keyword_index = indices.get("keyword_index", {})
                self.tag_index = indices.get("tag_index", {})
                self.topic_index = indices.get("topic_index", {})
                self.session_index = indices.get("session_index", {})

                if self.config.get("debug", False):
                    print(f"📚 加载索引: {len(self.keyword_index)}关键词, {len(self.tag_index)}标签")
            except Exception as e:
                print(f"加载索引失败: {e}")

    def _save_indices(self):
        """保存索引到磁盘"""
        index_file = self.index_dir / "indices.json"
        indices = {
            "keyword_index": self.keyword_index,
            "tag_index": self.tag_index,
            "topic_index": self.topic_index,
            "session_index": self.session_index,
            "last_updated": datetime.now().isoformat()
        }

        try:
            with open(index_file, 'w', encoding='utf-8') as f:
                json.dump(indices, f, ensure_ascii=False, indent=2)

            if self.config.get("debug", False):
                print(f"💾 索引已保存: {index_file}")
        except Exception as e:
            print(f"保存索引失败: {e}")

    def verify_and_store(self, fragment: Dict) -> Tuple[bool, str]:
        """验证并存储永久记忆片段

        核心约束：必须检查最终认证章，无有效认证章的片段一律拒绝

        Args:
            fragment: 记忆片段

        Returns:
            (success, message)
        """
        fragment_id = fragment.get("fragment_id")
        if not fragment_id:
            return False, "无效的片段ID"

        # 检查认证状态
        auth_status = fragment.get("auth_status", "")
        if auth_status != "final_approved":
            return False, f"无效的认证状态: {auth_status}，必须为final_approved"

        # 检查最终认证时间
        final_auth_time = fragment.get("final_auth_time")
        if not final_auth_time:
            return False, "缺少最终认证时间"

        # 检查是否已存在（版本管理）
        existing_fragment = self._get_fragment_by_id(fragment_id)
        if existing_fragment:
            # 已存在，检查是否需要更新
            return self._update_existing_fragment(existing_fragment, fragment)
        else:
            # 新片段，执行存储
            return self._store_new_fragment(fragment)

    def _store_new_fragment(self, fragment: Dict) -> Tuple[bool, str]:
        """存储新片段"""
        fragment_id = fragment.get("fragment_id")

        # 设置存储元数据
        fragment["stored_time"] = datetime.now().isoformat()
        fragment["version"] = "1.0"
        fragment["is_active"] = True
        fragment["last_accessed"] = fragment["stored_time"]

        # 保存片段文件
        fragment_file = self.long_term_dir / f"{fragment_id}.json"
        try:
            with open(fragment_file, 'w', encoding='utf-8') as f:
                json.dump(fragment, f, ensure_ascii=False, indent=2)

            # 更新索引
            self._update_indices_for_fragment(fragment)

            # 保存索引
            self._save_indices()

            if self.config.get("debug", False):
                print(f"💾 存储新片段: {fragment_id}")

            return True, f"片段 {fragment_id} 已成功存储"
        except Exception as e:
            return False, f"存储片段失败: {e}"

    def _update_existing_fragment(self, old_fragment: Dict, new_fragment: Dict) -> Tuple[bool, str]:
        """更新已存在的片段（版本管理）"""
        fragment_id = old_fragment.get("fragment_id")

        # 检查内容是否相同
        if self._are_fragments_identical(old_fragment, new_fragment):
            # 内容相同，只更新元数据
            old_fragment["last_accessed"] = datetime.now().isoformat()
            old_fragment["access_count"] = old_fragment.get("access_count", 0) + 1

            fragment_file = self.long_term_dir / f"{fragment_id}.json"
            try:
                with open(fragment_file, 'w', encoding='utf-8') as f:
                    json.dump(old_fragment, f, ensure_ascii=False, indent=2)
                return True, f"片段 {fragment_id} 已更新访问记录"
            except Exception as e:
                return False, f"更新片段失败: {e}"

        # 内容不同，创建新版本
        old_version = old_fragment.get("version", "1.0")
        try:
            # 解析版本号
            version_parts = old_version.split('.')
            if len(version_parts) == 2:
                major, minor = version_parts
                new_version = f"{major}.{int(minor) + 1}"
            else:
                new_version = f"{old_version}.1"
        except:
            new_version = "1.1"

        # 标记旧版本为过期
        old_fragment["is_active"] = False
        old_fragment["replaced_by"] = new_fragment["fragment_id"]
        old_fragment["replaced_time"] = datetime.now().isoformat()

        # 设置新片段元数据
        new_fragment["stored_time"] = datetime.now().isoformat()
        new_fragment["version"] = new_version
        new_fragment["is_active"] = True
        new_fragment["last_accessed"] = new_fragment["stored_time"]
        new_fragment["replaces"] = fragment_id

        # 保存旧版本
        old_fragment_file = self.long_term_dir / f"{fragment_id}_v{old_version}.json"
        try:
            with open(old_fragment_file, 'w', encoding='utf-8') as f:
                json.dump(old_fragment, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存旧版本失败: {e}")

        # 保存新版本
        new_fragment_file = self.long_term_dir / f"{new_fragment['fragment_id']}.json"
        try:
            with open(new_fragment_file, 'w', encoding='utf-8') as f:
                json.dump(new_fragment, f, ensure_ascii=False, indent=2)

            # 更新索引
            self._update_indices_for_fragment(new_fragment, is_update=True)

            # 保存索引
            self._save_indices()

            if self.config.get("debug", False):
                print(f"🔄 更新片段 {fragment_id}: v{old_version} -> v{new_version}")

            return True, f"片段 {fragment_id} 已更新到版本 {new_version}"
        except Exception as e:
            return False, f"更新片段失败: {e}"

    def _are_fragments_identical(self, frag1: Dict, frag2: Dict) -> bool:
        """检查两个片段是否相同"""
        # 比较内容
        if frag1.get("content") != frag2.get("content"):
            return False

        # 比较标签
        if set(frag1.get("topic_tags", [])) != set(frag2.get("topic_tags", [])):
            return False

        return True

    def _update_indices_for_fragment(self, fragment: Dict, is_update: bool = False):
        """为片段更新索引"""
        fragment_id = fragment.get("fragment_id")
        if not fragment_id:
            return

        # 如果是更新操作，先清理旧索引
        if is_update:
            self._remove_fragment_from_indices(fragment_id)

        # 1. 关键词索引
        keywords = self._extract_keywords(fragment.get("content", ""))
        for keyword in keywords:
            if keyword not in self.keyword_index:
                self.keyword_index[keyword] = []
            if fragment_id not in self.keyword_index[keyword]:
                self.keyword_index[keyword].append(fragment_id)

        # 2. 标签索引
        tags = fragment.get("topic_tags", [])
        for tag in tags:
            if tag not in self.tag_index:
                self.tag_index[tag] = []
            if fragment_id not in self.tag_index[tag]:
                self.tag_index[tag].append(fragment_id)

        # 3. 主题索引（使用主要标签作为主题）
        if tags:
            primary_topic = tags[0]  # 第一个标签作为主题
            if primary_topic not in self.topic_index:
                self.topic_index[primary_topic] = []
            if fragment_id not in self.topic_index[primary_topic]:
                self.topic_index[primary_topic].append(fragment_id)

        # 4. 会话索引
        session_id = fragment.get("session_id")
        if session_id:
            if session_id not in self.session_index:
                self.session_index[session_id] = []
            if fragment_id not in self.session_index[session_id]:
                self.session_index[session_id].append(fragment_id)

    def _remove_fragment_from_indices(self, fragment_id: str):
        """从索引中移除片段"""
        # 清理所有索引
        for index in [self.keyword_index, self.tag_index, self.topic_index, self.session_index]:
            for key, fragment_ids in list(index.items()):
                if fragment_id in fragment_ids:
                    fragment_ids.remove(fragment_id)
                # 如果键下没有片段了，移除该键
                if not fragment_ids:
                    del index[key]

    def _extract_keywords(self, content: str) -> List[str]:
        """从内容中提取关键词"""
        if self.config.get("keyword_extraction") == "tfidf":
            return self._extract_keywords_tfidf(content)
        else:
            return self._extract_keywords_basic(content)

    def _extract_keywords_basic(self, content: str) -> List[str]:
        """基础关键词提取"""
        keywords = []

        # 移除代码标记
        if content.startswith("```") and content.endswith("```"):
            # 提取代码语言和内容
            lines = content.split('\n')
            if len(lines) >= 2:
                content = '\n'.join(lines[1:-1])

        # 提取技术关键词
        tech_keywords = [
            # 编程语言
            "python", "java", "javascript", "typescript", "go", "rust", "c++", "c#",
            # 框架
            "fastapi", "django", "flask", "spring", "react", "vue", "angular",
            # 数据库
            "postgresql", "mysql", "mongodb", "redis", "sqlite",
            # 技术概念
            "api", "rest", "graphql", "websocket", "authentication", "authorization",
            "jwt", "oauth", "docker", "kubernetes", "aws", "azure", "gcp",
            "microservice", "monolith", "ci/cd", "devops"
        ]

        content_lower = content.lower()
        for keyword in tech_keywords:
            if keyword in content_lower:
                keywords.append(keyword)

        # 提取中文技术词
        chinese_tech = [
            "数据库", "缓存", "认证", "授权", "接口", "服务", "容器", "部署",
            "配置", "参数", "版本", "依赖", "安装", "编译", "测试", "调试",
            "性能", "安全", "日志", "监控", "备份", "恢复", "迁移", "升级"
        ]

        for keyword in chinese_tech:
            if keyword in content:
                keywords.append(keyword)

        # 限制关键词数量
        return list(set(keywords))[:10]  # 最多10个关键词

    def _extract_keywords_tfidf(self, content: str) -> List[str]:
        """TF-IDF关键词提取（简化版本）"""
        # MVP版本使用基础提取
        return self._extract_keywords_basic(content)

    def _get_fragment_by_id(self, fragment_id: str) -> Optional[Dict]:
        """根据ID获取片段"""
        fragment_file = self.long_term_dir / f"{fragment_id}.json"
        if not fragment_file.exists():
            # 检查是否有版本后缀
            for file_path in self.long_term_dir.glob(f"{fragment_id}_v*.json"):
                fragment_file = file_path
                break

        if fragment_file.exists():
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"读取片段文件失败 {fragment_file}: {e}")

        return None

    def retrieve_related_memories(self, user_input: str, context_tokens_remaining: int) -> List[Dict]:
        """检索与用户输入相关的记忆片段

        Args:
            user_input: 用户输入内容
            context_tokens_remaining: 上下文剩余token数量

        Returns:
            相关记忆片段列表，按相关性排序
        """
        if context_tokens_remaining <= 0:
            return []

        # 提取用户输入的关键词
        query_keywords = self._extract_keywords(user_input)
        query_tags = []  # 可以从历史中提取，这里简化

        if self.config.get("debug", False):
            print(f"🔍 检索记忆: 关键词={query_keywords}, 剩余token={context_tokens_remaining}")

        # 检索相关片段
        candidate_fragments = self._retrieve_candidates(query_keywords, query_tags, user_input)

        # 评分和排序
        scored_fragments = []
        for fragment_id, fragment in candidate_fragments:
            score = self._calculate_relevance_score(fragment, query_keywords, query_tags, user_input)
            scored_fragments.append((score, fragment_id, fragment))

        # 按评分排序
        scored_fragments.sort(key=lambda x: x[0], reverse=True)

        # 选择片段，不超过token限制
        selected_fragments = []
        total_tokens = 0
        max_tokens = int(context_tokens_remaining * self.config["max_injection_tokens"])

        for score, fragment_id, fragment in scored_fragments:
            fragment_tokens = fragment.get("token_count", 0)

            # 检查是否超过限制
            if total_tokens + fragment_tokens > max_tokens:
                if self.config.get("debug", False):
                    print(f"⚠️  跳过片段 {fragment_id}: token超出限制")
                continue

            # 检查最大片段数
            if len(selected_fragments) >= self.config["max_fragments_per_query"]:
                if self.config.get("debug", False):
                    print(f"⚠️  达到最大片段数限制")
                break

            # 添加片段
            selected_fragments.append(fragment)
            total_tokens += fragment_tokens

            # 更新访问记录
            self._update_fragment_access(fragment_id)

            if self.config.get("debug", False):
                print(f"  ✅ 选择片段 {fragment_id[:8]}: 评分={score:.2f}, token={fragment_tokens}")

        if self.config.get("debug", False):
            print(f"📋 检索完成: 选择了{len(selected_fragments)}个片段, 共{total_tokens} tokens")

        return selected_fragments

    def _retrieve_candidates(self, query_keywords: List[str], query_tags: List[str], user_input: str) -> List[Tuple[str, Dict]]:
        """检索候选片段"""
        candidates = {}

        # 1. 通过关键词检索
        for keyword in query_keywords:
            if keyword in self.keyword_index:
                for fragment_id in self.keyword_index[keyword]:
                    if fragment_id not in candidates:
                        fragment = self._get_fragment_by_id(fragment_id)
                        if fragment and fragment.get("is_active", True):
                            candidates[fragment_id] = fragment

        # 2. 通过标签检索
        for tag in query_tags:
            if tag in self.tag_index:
                for fragment_id in self.tag_index[tag]:
                    if fragment_id not in candidates:
                        fragment = self._get_fragment_by_id(fragment_id)
                        if fragment and fragment.get("is_active", True):
                            candidates[fragment_id] = fragment

        # 3. 模糊匹配（如果启用）
        if self.config.get("enable_fuzzy_match", True) and len(candidates) < 5:
            additional = self._fuzzy_match(user_input, list(candidates.keys()))
            for fragment_id, fragment in additional:
                if fragment_id not in candidates:
                    candidates[fragment_id] = fragment

        return list(candidates.items())

    def _fuzzy_match(self, query: str, exclude_ids: List[str]) -> List[Tuple[str, Dict]]:
        """模糊匹配"""
        results = []

        # 简单实现：检查所有活跃片段
        for fragment_file in self.long_term_dir.glob("*.json"):
            fragment_id = fragment_file.stem
            if fragment_id in exclude_ids or fragment_id.endswith("_v"):
                continue

            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                if not fragment.get("is_active", True):
                    continue

                # 简单文本匹配
                fragment_content = fragment.get("content", "").lower()
                query_lower = query.lower()

                # 检查是否有共同词
                fragment_words = set(re.findall(r'\b\w+\b', fragment_content))
                query_words = set(re.findall(r'\b\w+\b', query_lower))
                common_words = fragment_words & query_words

                if len(common_words) >= 2:  # 至少有2个共同词
                    results.append((fragment_id, fragment))

                if len(results) >= 10:  # 最多10个模糊匹配结果
                    break

            except Exception:
                continue

        return results

    def _calculate_relevance_score(self, fragment: Dict, query_keywords: List[str], query_tags: List[str], user_input: str) -> float:
        """计算片段相关性评分"""
        score = 0.0

        # 1. 关键词匹配
        fragment_keywords = self._extract_keywords(fragment.get("content", ""))
        keyword_overlap = len(set(fragment_keywords) & set(query_keywords))
        score += keyword_overlap * 5.0

        # 2. 标签匹配
        fragment_tags = fragment.get("topic_tags", [])
        tag_overlap = len(set(fragment_tags) & set(query_tags))
        score += tag_overlap * 8.0

        # 3. 文本相似度（简化）
        fragment_content = fragment.get("content", "").lower()
        query_lower = user_input.lower()

        # 检查子串匹配
        for word in query_lower.split():
            if len(word) > 3 and word in fragment_content:
                score += 2.0

        # 4. 时间衰减（新近性加分）
        stored_time = fragment.get("stored_time")
        if stored_time:
            try:
                stored_dt = datetime.fromisoformat(stored_time.replace('Z', '+00:00'))
                age_days = (datetime.now() - stored_dt).days
                # 新近性加分：30天内每少一天加0.1分
                if age_days < 30:
                    score += (30 - age_days) * 0.1
            except:
                pass

        # 5. 访问频率（热门内容加分）
        access_count = fragment.get("access_count", 0)
        score += min(access_count * 0.5, 10.0)  # 最多加10分

        # 6. 片段重要性（评分）
        fragment_score = fragment.get("score", 0)
        score += fragment_score * 0.1  # 原评分的10%

        return score

    def _update_fragment_access(self, fragment_id: str):
        """更新片段访问记录"""
        fragment_file = self.long_term_dir / f"{fragment_id}.json"
        if not fragment_file.exists():
            return

        try:
            with open(fragment_file, 'r', encoding='utf-8') as f:
                fragment = json.load(f)

            fragment["last_accessed"] = datetime.now().isoformat()
            fragment["access_count"] = fragment.get("access_count", 0) + 1

            with open(fragment_file, 'w', encoding='utf-8') as f:
                json.dump(fragment, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"更新片段访问记录失败 {fragment_id}: {e}")

    def format_memories_for_injection(self, fragments: List[Dict]) -> str:
        """将记忆片段格式化为上下文注入内容

        格式：
        【永久记忆回顾】
        1. [认证时间] [评分] [标签]
           内容摘要...
        """
        if not fragments:
            return ""

        lines = ["【永久记忆回顾】"]
        lines.append("以下是与当前对话相关的历史记忆：")
        lines.append("")

        for i, fragment in enumerate(fragments, 1):
            fragment_id = fragment.get("fragment_id", "")[:8]
            auth_time = fragment.get("final_auth_time", fragment.get("stored_time", ""))
            score = fragment.get("score", 0)
            tags = fragment.get("topic_tags", [])
            content_preview = self._generate_content_preview(fragment.get("content", ""))

            # 格式化时间
            if auth_time:
                try:
                    auth_dt = datetime.fromisoformat(auth_time.replace('Z', '+00:00'))
                    time_str = auth_dt.strftime("%Y-%m-%d %H:%M")
                except:
                    time_str = auth_time[:16]
            else:
                time_str = "未知时间"

            lines.append(f"{i}. [{time_str}] 评分:{score:.1f} 标签:{','.join(tags[:3])}")
            lines.append(f"   {content_preview}")
            lines.append("")

        return "\n".join(lines)

    def _generate_content_preview(self, content: str, max_length: int = 150) -> str:
        """生成内容预览"""
        if len(content) <= max_length:
            return content

        # 如果是代码，保留开头
        if content.startswith("```"):
            lines = content.split('\n')
            if len(lines) > 3:
                preview = '\n'.join(lines[:3]) + "\n..."
            else:
                preview = content[:max_length] + "..."
        else:
            preview = content[:max_length] + "..."

        return preview

    def cleanup_inactive_fragments(self, days_inactive: int = 180):
        """清理长时间未访问的非活跃片段"""
        cutoff_date = datetime.now() - timedelta(days=days_inactive)
        archived_count = 0

        for fragment_file in self.long_term_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                # 只处理非活跃或过期的片段
                if not fragment.get("is_active", True) or fragment.get("expired", False):
                    last_accessed = fragment.get("last_accessed")
                    if last_accessed:
                        try:
                            last_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                            if last_dt < cutoff_date:
                                # 移动到归档目录
                                archive_file = self.backup_dir / f"archived_{fragment_file.name}"
                                shutil.move(fragment_file, archive_file)
                                archived_count += 1

                                # 从索引中移除
                                fragment_id = fragment.get("fragment_id")
                                if fragment_id:
                                    self._remove_fragment_from_indices(fragment_id)
                        except:
                            pass
            except Exception as e:
                print(f"清理片段失败 {fragment_file}: {e}")

        if archived_count > 0:
            self._save_indices()

        if self.config.get("debug", False):
            print(f"🧹 清理了{archived_count}个非活跃片段")

        return archived_count

    def create_backup(self, backup_name: str = None) -> str:
        """创建备份"""
        if backup_name is None:
            backup_name = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        backup_path = self.backup_dir / backup_name
        backup_path.mkdir(exist_ok=True)

        # 备份长期记忆
        long_term_backup = backup_path / "long-term"
        shutil.copytree(self.long_term_dir, long_term_backup, dirs_exist_ok=True)

        # 备份索引
        index_backup = backup_path / "index"
        shutil.copytree(self.index_dir, index_backup, dirs_exist_ok=True)

        # 创建备份元数据
        metadata = {
            "backup_name": backup_name,
            "timestamp": datetime.now().isoformat(),
            "fragment_count": len(list(self.long_term_dir.glob("*.json"))),
            "index_sizes": {
                "keywords": len(self.keyword_index),
                "tags": len(self.tag_index),
                "topics": len(self.topic_index)
            }
        }

        metadata_file = backup_path / "metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        if self.config.get("debug", False):
            print(f"💾 创建备份: {backup_path}")

        return str(backup_path)

    def export_memories(self, format: str = "json", topic_filter: str = None) -> str:
        """导出记忆"""
        export_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_file = self.export_dir / f"memories_export_{export_time}.{format}"

        # 获取所有活跃片段
        fragments = []
        for fragment_file in self.long_term_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                if fragment.get("is_active", True):
                    # 应用主题过滤
                    if topic_filter:
                        tags = fragment.get("topic_tags", [])
                        if topic_filter.lower() not in [tag.lower() for tag in tags]:
                            continue

                    fragments.append(fragment)
            except:
                continue

        if format == "json":
            export_data = {
                "export_time": datetime.now().isoformat(),
                "fragment_count": len(fragments),
                "fragments": fragments
            }

            with open(export_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

        elif format == "markdown":
            with open(export_file, 'w', encoding='utf-8') as f:
                f.write(f"# 记忆导出\n\n")
                f.write(f"导出时间: {datetime.now().isoformat()}\n")
                f.write(f"片段数量: {len(fragments)}\n\n")

                for i, fragment in enumerate(fragments, 1):
                    f.write(f"## 片段 {i}: {fragment.get('fragment_id', '')[:8]}\n\n")
                    f.write(f"**评分**: {fragment.get('score', 0):.1f}\n")
                    f.write(f"**标签**: {', '.join(fragment.get('topic_tags', []))}\n")
                    f.write(f"**存储时间**: {fragment.get('stored_time', '')}\n")
                    f.write(f"**最后访问**: {fragment.get('last_accessed', '')}\n\n")

                    content = fragment.get("content", "")
                    if fragment.get("content_type") == "code":
                        f.write("```python\n")
                        f.write(content[:500])
                        if len(content) > 500:
                            f.write("\n...")
                        f.write("\n```\n")
                    else:
                        f.write(f"{content[:300]}")
                        if len(content) > 300:
                            f.write("...")
                        f.write("\n")

                    f.write("\n---\n\n")

        if self.config.get("debug", False):
            print(f"📤 导出完成: {export_file} ({len(fragments)}个片段)")

        return str(export_file)

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            "total_fragments": 0,
            "active_fragments": 0,
            "inactive_fragments": 0,
            "total_tokens": 0,
            "index_sizes": {
                "keywords": len(self.keyword_index),
                "tags": len(self.tag_index),
                "topics": len(self.topic_index),
                "sessions": len(self.session_index)
            },
            "recent_activity": {
                "last_week_access": 0,
                "last_month_access": 0
            }
        }

        one_week_ago = datetime.now() - timedelta(days=7)
        one_month_ago = datetime.now() - timedelta(days=30)

        for fragment_file in self.long_term_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                stats["total_fragments"] += 1
                stats["total_tokens"] += fragment.get("token_count", 0)

                if fragment.get("is_active", True):
                    stats["active_fragments"] += 1
                else:
                    stats["inactive_fragments"] += 1

                # 检查最近访问
                last_accessed = fragment.get("last_accessed")
                if last_accessed:
                    try:
                        last_dt = datetime.fromisoformat(last_accessed.replace('Z', '+00:00'))
                        if last_dt > one_week_ago:
                            stats["recent_activity"]["last_week_access"] += 1
                        if last_dt > one_month_ago:
                            stats["recent_activity"]["last_month_access"] += 1
                    except:
                        pass

            except Exception as e:
                print(f"统计片段失败 {fragment_file}: {e}")

        return stats


# 简单的命令行测试
if __name__ == "__main__":
    print("🧠 测试大脑皮层Agent...")

    # 创建测试目录
    test_dir = Path("test_cortex")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 初始化Agent
    cortex = CortexAgent(str(test_dir))

    # 创建测试片段
    test_fragment = {
        "fragment_id": "test_cortex_001",
        "content": "API认证必须使用JWT token，有效期24小时。需要支持refresh token机制，refresh token有效期7天。",
        "content_type": "text",
        "topic_tags": ["authentication", "security", "jwt", "api"],
        "score": 88.5,
        "auth_status": "final_approved",
        "final_auth_time": datetime.now().isoformat(),
        "token_count": 35,
        "session_id": "test_session_001"
    }

    print("\n💾 测试存储片段...")
    success, message = cortex.verify_and_store(test_fragment)
    print(f"存储结果: {success}, {message}")

    # 创建另一个片段（相同主题，不同内容）
    test_fragment2 = {
        "fragment_id": "test_cortex_002",
        "content": "import jwt\nfrom datetime import datetime, timedelta\n\nSECRET_KEY = 'your-secret-key'\nALGORITHM = 'HS256'\n\ndef create_jwt_token(user_id: str):\n    payload = {\n        'user_id': user_id,\n        'exp': datetime.utcnow() + timedelta(hours=24)\n    }\n    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)\n    return token",
        "content_type": "code",
        "topic_tags": ["python", "jwt", "code", "authentication"],
        "score": 92.0,
        "auth_status": "final_approved",
        "final_auth_time": datetime.now().isoformat(),
        "token_count": 65,
        "session_id": "test_session_001"
    }

    print("\n💾 存储第二个片段...")
    success, message = cortex.verify_and_store(test_fragment2)
    print(f"存储结果: {success}, {message}")

    # 测试检索
    print("\n🔍 测试检索相关记忆...")
    test_query = "如何实现JWT认证？需要Python代码示例。"
    related_memories = cortex.retrieve_related_memories(test_query, context_tokens_remaining=1000)

    print(f"检索到{len(related_memories)}个相关片段:")
    for i, fragment in enumerate(related_memories, 1):
        print(f"  {i}. {fragment['fragment_id'][:8]}: {fragment['content'][:50]}...")

    # 测试格式化注入
    print("\n📋 测试格式化注入...")
    injection_text = cortex.format_memories_for_injection(related_memories)
    print("注入内容预览:")
    print("-" * 50)
    print(injection_text[:300])
    if len(injection_text) > 300:
        print("...")
    print("-" * 50)

    # 测试统计信息
    print("\n📊 测试统计信息...")
    stats = cortex.get_stats()
    print(f"统计信息:")
    print(f"  - 总片段数: {stats['total_fragments']}")
    print(f"  - 活跃片段: {stats['active_fragments']}")
    print(f"  - 总token数: {stats['total_tokens']}")
    print(f"  - 关键词索引: {stats['index_sizes']['keywords']}")

    # 测试备份
    print("\n💾 测试备份...")
    backup_path = cortex.create_backup("test_backup")
    print(f"备份路径: {backup_path}")

    # 测试导出
    print("\n📤 测试导出...")
    export_path = cortex.export_memories(format="markdown")
    print(f"导出路径: {export_path}")

    print("\n✅ 测试完成")
    print(f"测试目录: {test_dir}")
    print("你可以查看生成的备份和导出文件")