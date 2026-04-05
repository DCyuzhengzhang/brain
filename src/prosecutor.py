#!/usr/bin/env python3
"""
组蛋白甲基转移酶Agent - 记忆筛选与认证
神经科学对应：组蛋白甲基转移酶EHMT1介导的记忆印记表观遗传门控机制

核心职责：
1. 记忆片段初筛与量化打分（0-100分）
2. 初级认证盖章（评分≥60分→「待用户确认」）
3. 反馈二次认证（用户确认→「永久存储准入」）
4. 认证规则迭代
5. 全链路认证追溯
"""

import os
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
import copy

@dataclass
class ScoringRule:
    """评分规则"""
    name: str
    description: str
    keywords: List[str]
    weight: float
    max_score: float
    applies_to: str  # "text", "code", "both"

@dataclass
class AuthRecord:
    """认证记录"""
    fragment_id: str
    timestamp: str
    operation: str  # "primary_screening", "user_feedback", "secondary_auth"
    score: float
    auth_status: str
    notes: str = ""

class ProsecutorAgent:
    """组蛋白甲基转移酶Agent - 盖章认证检察官·记忆筛选门控"""

    def __init__(self, data_dir: str = None):
        """初始化检察官Agent

        Args:
            data_dir: 数据存储目录
        """
        if data_dir is None:
            home = os.path.expanduser("~")
            self.data_dir = Path(home) / ".claude" / "plugins" / "memory"
        else:
            self.data_dir = Path(data_dir)

        # 创建必要的目录
        self.auth_dir = self.data_dir / "auth-records"
        self.temp_auth_dir = self.data_dir / "temp-auth"  # 待确认片段
        self.final_auth_dir = self.data_dir / "final-auth"  # 最终认证片段
        self.archive_dir = self.data_dir / "archive"  # 归档无效片段

        for dir_path in [self.auth_dir, self.temp_auth_dir, self.final_auth_dir, self.archive_dir]:
            dir_path.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

        # 初始化评分规则
        self.scoring_rules = self._init_scoring_rules()

        # 历史记录
        self.auth_history = []

    def _load_config(self) -> Dict:
        """加载配置文件"""
        config_file = self.data_dir / "config" / "config.json"
        default_config = {
            "score_threshold": 60.0,  # 初级认证阈值
            "user_override_enabled": True,  # 允许用户覆盖
            "auto_auth_disabled": True,  # 默认禁用自动认证
            "debug": False,
            # 评分权重
            "weights": {
                "code_logic": 1.5,
                "requirement": 1.3,
                "constraint": 1.4,
                "technical_detail": 1.2,
                "error_correction": 1.3,
                "environment_config": 1.1,
                "user_emphasis": 1.6
            }
        }

        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                default_config.update(user_config)
            except Exception as e:
                print(f"加载配置文件失败，使用默认配置: {e}")

        return default_config

    def _init_scoring_rules(self) -> List[ScoringRule]:
        """初始化评分规则"""
        rules = [
            # 代码核心逻辑
            ScoringRule(
                name="代码核心逻辑",
                description="包含函数、类、算法等代码实现逻辑",
                keywords=[
                    "def ", "class ", "function ", "return ", "if ", "for ", "while ",
                    "import ", "from ", "try:", "except:", "with ",
                    "算法", "逻辑", "实现", "方法", "函数", "类"
                ],
                weight=self.config["weights"]["code_logic"],
                max_score=30.0,
                applies_to="code"
            ),

            # 用户需求核心约束
            ScoringRule(
                name="需求核心约束",
                description="用户明确表达的需求、要求、必须条件",
                keywords=[
                    "需要", "要求", "必须", "要", "需求", "should", "must", "require",
                    "核心", "关键", "重要", "essential", "critical", "important"
                ],
                weight=self.config["weights"]["requirement"],
                max_score=25.0,
                applies_to="both"
            ),

            # 技术约束与禁止
            ScoringRule(
                name="技术约束与禁止",
                description="用户明确禁止或限制的技术选择",
                keywords=[
                    "不能", "禁止", "不要", "避免", "cannot", "must not", "avoid",
                    "限制", "不支持", "不允许", "禁止使用", "不要用",
                    "必须使用", "只能", "仅限", "only", "exclusive"
                ],
                weight=self.config["weights"]["constraint"],
                max_score=25.0,
                applies_to="both"
            ),

            # 关键技术参数
            ScoringRule(
                name="关键技术参数",
                description="具体的技术规格、参数、配置",
                keywords=[
                    "版本", "v", "version", "配置", "参数", "设置", "setting",
                    "端口", "port", "地址", "address", "URL", "路径", "path",
                    "数据库", "database", "表", "table", "字段", "field",
                    "API", "接口", "endpoint", "请求", "request", "响应", "response"
                ],
                weight=self.config["weights"]["technical_detail"],
                max_score=20.0,
                applies_to="both"
            ),

            # 错误修正记录
            ScoringRule(
                name="错误修正记录",
                description="bug修复、错误处理、问题解决",
                keywords=[
                    "错误", "bug", "问题", "修复", "解决", "error", "fix", "issue",
                    "调试", "debug", "异常", "exception", "失败", "fail",
                    "警告", "warning", "检查", "check", "验证", "validate"
                ],
                weight=self.config["weights"]["error_correction"],
                max_score=20.0,
                applies_to="both"
            ),

            # 环境配置信息
            ScoringRule(
                name="环境配置信息",
                description="环境变量、配置文件、依赖库",
                keywords=[
                    "环境", "环境变量", "ENV", "config", "配置文件", ".env",
                    "依赖", "dependencies", "安装", "install", "包", "package",
                    "路径", "directory", "文件夹", "folder", "文件", "file"
                ],
                weight=self.config["weights"]["environment_config"],
                max_score=15.0,
                applies_to="both"
            ),

            # 用户明确强调的内容
            ScoringRule(
                name="用户明确强调",
                description="用户使用强调标记或重复强调的内容",
                keywords=[],  # 特殊规则，基于格式检测
                weight=self.config["weights"]["user_emphasis"],
                max_score=30.0,
                applies_to="both"
            ),

            # 高频重复需求检测
            ScoringRule(
                name="高频重复",
                description="同一内容在对话中多次出现",
                keywords=[],  # 特殊规则，基于历史统计
                weight=1.0,
                max_score=15.0,
                applies_to="both"
            )
        ]

        return rules

    def primary_screening(self, fragments: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """初级认证筛选

        Args:
            fragments: 海马体推送的记忆片段列表

        Returns:
            (primary_approved, invalid_fragments)
            - primary_approved: 评分≥阈值，加盖初级认证章的片段
            - invalid_fragments: 评分＜阈值的无效片段
        """
        if not fragments:
            return [], []

        primary_approved = []
        invalid_fragments = []

        if self.config.get("debug", False):
            print(f"🔍 开始初级认证筛选，共{len(fragments)}个片段")

        for fragment in fragments:
            fragment_id = fragment.get("fragment_id", "unknown")

            try:
                # 评分
                score_result = self._score_fragment(fragment)
                fragment["score"] = score_result["total_score"]
                fragment["score_details"] = score_result["details"]

                # 记录认证
                auth_record = AuthRecord(
                    fragment_id=fragment_id,
                    timestamp=datetime.now().isoformat(),
                    operation="primary_screening",
                    score=fragment["score"],
                    auth_status="primary_approved" if fragment["score"] >= self.config["score_threshold"] else "invalid",
                    notes=f"评分: {fragment['score']:.1f}, 阈值: {self.config['score_threshold']}"
                )

                self._save_auth_record(auth_record)

                # 分类
                if fragment["score"] >= self.config["score_threshold"]:
                    # 加盖初级认证章
                    fragment["auth_status"] = "primary_approved"
                    fragment["primary_auth_time"] = datetime.now().isoformat()

                    primary_approved.append(fragment)

                    if self.config.get("debug", False):
                        print(f"  ✅ 片段 {fragment_id[:8]}... 评分: {fragment['score']:.1f} → 初级认证")
                else:
                    # 标记为无效
                    fragment["auth_status"] = "invalid"
                    fragment["invalid_reason"] = f"评分不足: {fragment['score']:.1f} < {self.config['score_threshold']}"

                    invalid_fragments.append(fragment)

                    if self.config.get("debug", False):
                        print(f"  ❌ 片段 {fragment_id[:8]}... 评分: {fragment['score']:.1f} → 无效")

            except Exception as e:
                print(f"⚠️  处理片段 {fragment_id} 失败: {e}")
                fragment["auth_status"] = "error"
                fragment["error"] = str(e)
                invalid_fragments.append(fragment)

        return primary_approved, invalid_fragments

    def _score_fragment(self, fragment: Dict) -> Dict:
        """对记忆片段进行多维度评分

        Returns:
            {
                "total_score": float,
                "details": [
                    {"rule": str, "score": float, "weighted": float, "reason": str}
                ]
            }
        """
        content = fragment.get("content", "").lower()
        content_type = fragment.get("content_type", "text")
        topic_tags = fragment.get("topic_tags", [])

        details = []
        total_score = 0.0

        # 应用每个评分规则
        for rule in self.scoring_rules:
            # 检查适用性
            if rule.applies_to != "both" and rule.applies_to != content_type:
                continue

            # 特殊规则处理
            if rule.name == "用户明确强调":
                rule_score = self._score_user_emphasis(fragment)
            elif rule.name == "高频重复":
                rule_score = self._score_repetition(fragment)
            else:
                # 关键词匹配评分
                rule_score = self._score_by_keywords(content, rule)

            # 加权计算
            weighted_score = rule_score * rule.weight
            details.append({
                "rule": rule.name,
                "score": rule_score,
                "weighted": weighted_score,
                "reason": f"匹配关键词或格式"
            })

            total_score += weighted_score

        # 额外加分：代码片段基础分
        if content_type == "code":
            total_score += 10.0
            details.append({
                "rule": "代码片段基础分",
                "score": 10.0,
                "weighted": 10.0,
                "reason": "代码内容"
            })

        # 额外加分：重要标签
        important_tags = {"requirement", "constraint", "code", "technical"}
        tag_bonus = len(set(topic_tags) & important_tags) * 3.0
        if tag_bonus > 0:
            total_score += tag_bonus
            details.append({
                "rule": "重要标签加分",
                "score": tag_bonus,
                "weighted": tag_bonus,
                "reason": f"标签: {topic_tags}"
            })

        # 限制在0-100分范围内
        total_score = max(0.0, min(100.0, total_score))

        return {
            "total_score": total_score,
            "details": details
        }

    def _score_by_keywords(self, content: str, rule: ScoringRule) -> float:
        """基于关键词匹配评分"""
        if not rule.keywords:
            return 0.0

        # 统计关键词出现次数
        match_count = 0
        for keyword in rule.keywords:
            if keyword.lower() in content:
                match_count += 1

        if match_count == 0:
            return 0.0

        # 根据匹配次数计算分数
        base_score = min(match_count * 5.0, rule.max_score)

        # 检查是否在关键位置出现（开头附近）
        for keyword in rule.keywords:
            if keyword.lower() in content:
                # 计算位置权重
                position = content.find(keyword.lower())
                if position >= 0 and position < 100:  # 在前100字符内
                    position_bonus = 3.0
                    base_score += position_bonus
                    break

        return min(base_score, rule.max_score)

    def _score_user_emphasis(self, fragment: Dict) -> float:
        """评分用户明确强调的内容"""
        content = fragment.get("content", "")
        score = 0.0

        # 检测强调格式
        emphasis_patterns = [
            (r'注意[：:]', 10.0),
            (r'重要[：:]', 8.0),
            (r'核心[：:]', 8.0),
            (r'关键[：:]', 8.0),
            (r'必须[：:]', 8.0),
            (r'!!!', 5.0),
            (r'!!!', 5.0),
            (r'【重要】', 10.0),
            (r'【核心】', 8.0),
            (r'【注意】', 8.0),
        ]

        for pattern, pattern_score in emphasis_patterns:
            if re.search(pattern, content):
                score += pattern_score

        # 检测重复强调（同一句话出现多次）
        sentences = re.split(r'[。！？\n]', content)
        sentence_count = {}
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 10:  # 忽略过短的句子
                sentence_count[sentence] = sentence_count.get(sentence, 0) + 1

        for count in sentence_count.values():
            if count >= 2:
                score += 5.0 * (count - 1)

        # 检测感叹号数量
        exclamation_count = content.count('!') + content.count('！')
        if exclamation_count >= 3:
            score += min(exclamation_count * 2.0, 10.0)

        return min(score, 30.0)  # 不超过规则上限

    def _score_repetition(self, fragment: Dict) -> float:
        """评分高频重复需求"""
        # 简化版本：检查相似片段的历史出现
        # 实际实现需要访问历史记录
        return 0.0  # MVP版本暂不实现

    def _save_auth_record(self, record: AuthRecord):
        """保存认证记录"""
        record_file = self.auth_dir / f"{record.fragment_id}_{record.timestamp.replace(':', '-')}.json"

        record_dict = {
            "fragment_id": record.fragment_id,
            "timestamp": record.timestamp,
            "operation": record.operation,
            "score": record.score,
            "auth_status": record.auth_status,
            "notes": record.notes
        }

        try:
            with open(record_file, 'w', encoding='utf-8') as f:
                json.dump(record_dict, f, ensure_ascii=False, indent=2)

            self.auth_history.append(record_dict)
        except Exception as e:
            print(f"保存认证记录失败: {e}")

    def save_primary_approved(self, fragments: List[Dict]):
        """保存初级认证通过的片段（待用户确认）"""
        for fragment in fragments:
            fragment_id = fragment.get("fragment_id")
            if not fragment_id:
                continue

            fragment_file = self.temp_auth_dir / f"{fragment_id}.json"

            # 添加认证信息
            fragment["primary_auth_time"] = datetime.now().isoformat()
            fragment["auth_status"] = "primary_approved"
            fragment["needs_user_confirmation"] = True

            try:
                with open(fragment_file, 'w', encoding='utf-8') as f:
                    json.dump(fragment, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存初级认证片段失败 {fragment_id}: {e}")

    def archive_invalid_fragments(self, fragments: List[Dict]):
        """归档无效片段"""
        for fragment in fragments:
            fragment_id = fragment.get("fragment_id")
            if not fragment_id:
                continue

            fragment_file = self.archive_dir / f"{fragment_id}.json"

            # 添加归档信息
            fragment["archived_time"] = datetime.now().isoformat()
            fragment["archived_reason"] = fragment.get("invalid_reason", "评分不足")

            try:
                with open(fragment_file, 'w', encoding='utf-8') as f:
                    json.dump(fragment, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"归档无效片段失败 {fragment_id}: {e}")

    def get_pending_confirmation(self) -> List[Dict]:
        """获取待用户确认的片段"""
        pending_fragments = []

        for fragment_file in self.temp_auth_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                if fragment.get("needs_user_confirmation", False):
                    pending_fragments.append(fragment)

            except Exception as e:
                print(f"读取待确认片段失败 {fragment_file}: {e}")

        # 按评分排序
        pending_fragments.sort(key=lambda x: x.get("score", 0), reverse=True)

        return pending_fragments

    def process_user_feedback(self, feedback_data: Dict) -> Tuple[List[Dict], List[Dict], List[Dict]]:
        """处理用户反馈，进行二次认证

        Args:
            feedback_data: {
                "session_id": str,
                "fragment_decisions": [
                    {"fragment_id": str, "decision": "keep"/"delete"/"later"},
                    ...
                ],
                "user_notes": str (optional)
            }

        Returns:
            (final_approved, to_delete, to_later)
        """
        final_approved = []
        to_delete = []
        to_later = []

        if not feedback_data or "fragment_decisions" not in feedback_data:
            return final_approved, to_delete, to_later

        for decision in feedback_data["fragment_decisions"]:
            fragment_id = decision.get("fragment_id")
            user_decision = decision.get("decision", "").lower()

            if not fragment_id:
                continue

            # 查找片段
            fragment_file = self.temp_auth_dir / f"{fragment_id}.json"
            if not fragment_file.exists():
                print(f"⚠️  找不到片段 {fragment_id}")
                continue

            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                # 记录用户反馈
                fragment["user_feedback"] = user_decision
                fragment["user_feedback_time"] = datetime.now().isoformat()

                auth_record = AuthRecord(
                    fragment_id=fragment_id,
                    timestamp=datetime.now().isoformat(),
                    operation="user_feedback",
                    score=fragment.get("score", 0),
                    auth_status=f"user_{user_decision}",
                    notes=f"用户反馈: {user_decision}"
                )

                self._save_auth_record(auth_record)

                # 根据用户决定处理
                if user_decision == "keep":
                    # 加盖最终认证章
                    fragment["auth_status"] = "final_approved"
                    fragment["final_auth_time"] = datetime.now().isoformat()
                    fragment["needs_user_confirmation"] = False

                    final_approved.append(fragment)

                    # 移动到最终认证目录
                    final_file = self.final_auth_dir / f"{fragment_id}.json"
                    with open(final_file, 'w', encoding='utf-8') as f:
                        json.dump(fragment, f, ensure_ascii=False, indent=2)

                    # 删除临时文件
                    fragment_file.unlink(missing_ok=True)

                    if self.config.get("debug", False):
                        print(f"  ✅ 用户确认保留: {fragment_id[:8]}...")

                elif user_decision == "delete":
                    # 标记删除
                    fragment["auth_status"] = "user_deleted"
                    fragment["deleted_time"] = datetime.now().isoformat()

                    to_delete.append(fragment)

                    # 归档
                    self.archive_invalid_fragments([fragment])

                    # 删除临时文件
                    fragment_file.unlink(missing_ok=True)

                    if self.config.get("debug", False):
                        print(f"  ❌ 用户确认删除: {fragment_id[:8]}...")

                elif user_decision == "later":
                    # 标记为稍后处理
                    fragment["auth_status"] = "pending_later"
                    fragment["pending_until"] = datetime.now().isoformat()

                    to_later.append(fragment)

                    if self.config.get("debug", False):
                        print(f"  ⏸️  用户稍后确认: {fragment_id[:8]}...")

            except Exception as e:
                print(f"处理用户反馈失败 {fragment_id}: {e}")

        return final_approved, to_delete, to_later

    def get_final_approved(self) -> List[Dict]:
        """获取最终认证通过的片段"""
        final_fragments = []

        for fragment_file in self.final_auth_dir.glob("*.json"):
            try:
                with open(fragment_file, 'r', encoding='utf-8') as f:
                    fragment = json.load(f)

                if fragment.get("auth_status") == "final_approved":
                    final_fragments.append(fragment)

            except Exception as e:
                print(f"读取最终认证片段失败 {fragment_file}: {e}")

        return final_fragments

    def update_scoring_rules(self, feedback_data: Dict):
        """基于用户反馈更新评分规则

        Args:
            feedback_data: {
                "correct_decisions": [
                    {"fragment_id": str, "expected_decision": str, "actual_decision": str}
                ],
                "user_adjustments": {
                    "rule_weights": {rule_name: new_weight},
                    "keywords": {rule_name: [new_keywords]}
                }
            }
        """
        # 简化版本：记录反馈，实际更新需要更复杂的算法
        feedback_file = self.auth_dir / f"rule_feedback_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with open(feedback_file, 'w', encoding='utf-8') as f:
                json.dump(feedback_data, f, ensure_ascii=False, indent=2)

            if self.config.get("debug", False):
                print(f"📊 记录评分规则反馈: {feedback_file}")
        except Exception as e:
            print(f"保存规则反馈失败: {e}")

    def get_stats(self) -> Dict:
        """获取统计信息"""
        stats = {
            "total_processed": len(self.auth_history),
            "primary_approved": 0,
            "final_approved": 0,
            "user_deleted": 0,
            "invalid": 0,
            "pending": 0
        }

        for record in self.auth_history:
            if "primary_approved" in record.get("auth_status", ""):
                stats["primary_approved"] += 1
            elif "final_approved" in record.get("auth_status", ""):
                stats["final_approved"] += 1
            elif "user_deleted" in record.get("auth_status", ""):
                stats["user_deleted"] += 1
            elif "invalid" in record.get("auth_status", ""):
                stats["invalid"] += 1
            elif "pending" in record.get("auth_status", ""):
                stats["pending"] += 1

        # 文件统计
        stats["files_pending"] = len(list(self.temp_auth_dir.glob("*.json")))
        stats["files_final"] = len(list(self.final_auth_dir.glob("*.json")))
        stats["files_archive"] = len(list(self.archive_dir.glob("*.json")))

        return stats


# 简单的命令行测试
if __name__ == "__main__":
    print("⚖️  测试检察官Agent...")

    # 创建测试目录
    test_dir = Path("test_prosecutor")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir()

    # 初始化Agent
    prosecutor = ProsecutorAgent(str(test_dir))

    # 创建测试片段
    test_fragments = [
        {
            "fragment_id": "test_001",
            "content": "注意：这个API必须使用JWT认证，不能使用Basic Auth。版本要求Python 3.9以上。",
            "content_type": "text",
            "topic_tags": ["requirement", "constraint", "technical"],
            "auth_status": "unprocessed"
        },
        {
            "fragment_id": "test_002",
            "content": "import fastapi\nfrom fastapi import FastAPI\n\napp = FastAPI()\n\n@app.get('/')\ndef read_root():\n    return {'Hello': 'World'}",
            "content_type": "code",
            "topic_tags": ["python", "code"],
            "auth_status": "unprocessed"
        },
        {
            "fragment_id": "test_003",
            "content": "今天天气不错，我们下午去吃饭吧。",
            "content_type": "text",
            "topic_tags": [],
            "auth_status": "unprocessed"
        }
    ]

    # 初级筛选
    print("\n🔍 进行初级筛选...")
    primary_approved, invalid_fragments = prosecutor.primary_screening(test_fragments)

    print(f"✅ 初级认证通过: {len(primary_approved)} 个片段")
    print(f"❌ 无效片段: {len(invalid_fragments)} 个片段")

    for fragment in primary_approved:
        print(f"  - {fragment['fragment_id']}: 评分 {fragment['score']:.1f}")

    # 保存初级认证片段
    prosecutor.save_primary_approved(primary_approved)
    prosecutor.archive_invalid_fragments(invalid_fragments)

    # 获取待确认片段
    pending = prosecutor.get_pending_confirmation()
    print(f"\n⏳ 待用户确认: {len(pending)} 个片段")

    # 模拟用户反馈
    print("\n👤 模拟用户反馈处理...")
    feedback_data = {
        "session_id": "test_session",
        "fragment_decisions": [
            {"fragment_id": "test_001", "decision": "keep"},
            {"fragment_id": "test_002", "decision": "keep"},
            {"fragment_id": "test_003", "decision": "delete"}
        ],
        "user_notes": "测试反馈"
    }

    final_approved, to_delete, to_later = prosecutor.process_user_feedback(feedback_data)

    print(f"✅ 最终认证: {len(final_approved)} 个片段")
    print(f"❌ 用户删除: {len(to_delete)} 个片段")
    print(f"⏸️  稍后处理: {len(to_later)} 个片段")

    # 获取统计信息
    stats = prosecutor.get_stats()
    print(f"\n📊 统计信息: {stats}")

    print("\n✅ 测试完成")
    # 保留测试目录供检查