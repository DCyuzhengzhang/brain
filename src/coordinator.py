#!/usr/bin/env python3
"""
记忆管理系统主协调器
负责四Agent协同工作流程的调度与集成
"""

import os
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import sys

# 添加src目录到路径，以便导入其他模块
sys.path.append(str(Path(__file__).parent))

from hippocampus import HippocampusAgent
from prosecutor import ProsecutorAgent
from thalamus import ThalamusAgent
from cortex import CortexAgent

class MemoryCoordinator:
    """记忆管理系统主协调器"""

    def __init__(self, data_dir: str = None, auto_init: bool = True):
        """初始化协调器

        Args:
            data_dir: 数据存储目录
            auto_init: 是否自动初始化所有Agent
        """
        if data_dir is None:
            home = os.path.expanduser("~")
            self.data_dir = Path(home) / ".claude" / "plugins" / "memory"
        else:
            self.data_dir = Path(data_dir)

        # 创建配置目录
        self.config_dir = self.data_dir / "config"
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.config = self._load_config()

        # 初始化Agent
        self.hippocampus = None
        self.prosecutor = None
        self.thalamus = None
        self.cortex = None

        if auto_init:
            self.initialize_agents()

        # 状态跟踪
        self.current_session_id = None
        self.is_running = False

    def _load_config(self) -> Dict:
        """加载配置"""
        config_file = self.config_dir / "config.json"
        default_config = {
            # 核心配置
            "enabled": True,
            "auto_start": True,
            "debug": False,

            # 海马体配置
            "token_threshold": 25000,
            "warning_threshold": 20000,  # 80%阈值
            "min_fragment_tokens": 128,
            "max_fragment_tokens": 1024,

            # 检察官配置
            "score_threshold": 60.0,
            "user_override_enabled": True,
            "auto_auth_disabled": True,

            # 丘脑前部配置
            "feedback_timeout_hours": 72,
            "max_fragments_per_interaction": 20,
            "silent_mode": False,
            "silent_hours": "9:00-18:00",

            # 大脑皮层配置
            "max_injection_tokens": 0.2,  # 20%
            "max_fragments_per_query": 5,
            "backup_frequency_days": 1,

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
                print(f"[WARNING] 加载配置文件失败，使用默认配置: {e}")

        return default_config

    def save_config(self):
        """保存配置"""
        config_file = self.config_dir / "config.json"
        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)

            if self.config.get("debug", False):
                print(f"[SAVE] 配置已保存: {config_file}")
        except Exception as e:
            print(f"保存配置失败: {e}")

    def initialize_agents(self):
        """初始化所有Agent"""
        try:
            self.hippocampus = HippocampusAgent(str(self.data_dir))
            self.prosecutor = ProsecutorAgent(str(self.data_dir))
            self.thalamus = ThalamusAgent(str(self.data_dir))
            self.cortex = CortexAgent(str(self.data_dir))

            if self.config.get("debug", False):
                print("[OK] 所有Agent初始化完成")

            return True
        except Exception as e:
            print(f"[ERROR] Agent初始化失败: {e}")
            return False

    def start_session(self, session_id: str = None) -> str:
        """开始新的记忆管理会话"""
        if not self.hippocampus:
            if not self.initialize_agents():
                return None

        self.current_session_id = self.hippocampus.start_new_session(session_id)
        self.is_running = True

        if self.config.get("debug", False):
            print(f"[START] 开始记忆管理会话: {self.current_session_id}")

        return self.current_session_id

    def record_conversation_turn(self, user_input: str, claude_output: str) -> Dict:
        """记录单轮对话

        这是主入口点，在每轮对话后调用
        """
        if not self.is_running:
            self.start_session()

        if not self.hippocampus:
            return {"status": "error", "message": "海马体Agent未初始化"}

        try:
            # 1. 记录对话到海马体
            record_result = self.hippocampus.record_turn(user_input, claude_output)

            # 2. 检查是否需要触发记忆巩固
            if record_result.get("should_consolidate", False):
                if self.config.get("debug", False):
                    print(f"[TARGET] 达到阈值，触发记忆巩固: {record_result['total_tokens']} tokens")

                # 启动记忆巩固流程
                consolidation_result = self.trigger_memory_consolidation()

                record_result["consolidation_triggered"] = True
                record_result["consolidation_result"] = consolidation_result
            else:
                record_result["consolidation_triggered"] = False

            # 3. 向用户显示警告（如果接近阈值）
            if record_result.get("threshold_warning", False):
                record_result["warning_message"] = f"[WARNING] 对话token接近阈值: {record_result['total_tokens']}/{self.config['token_threshold']}"

            return record_result

        except Exception as e:
            return {"status": "error", "message": f"记录对话失败: {str(e)}"}

    def trigger_memory_consolidation(self) -> Dict:
        """触发记忆巩固流程

        完整流程：
        1. 海马体提供未处理片段
        2. 检察官初级筛选
        3. 丘脑前部用户交互
        4. 检察官二次认证
        5. 大脑皮层永久存储
        """
        if not all([self.hippocampus, self.prosecutor, self.thalamus, self.cortex]):
            return {"status": "error", "message": "Agent未完全初始化"}

        try:
            results = {
                "status": "started",
                "timestamp": datetime.now().isoformat(),
                "steps": {}
            }

            # 步骤1: 从海马体获取未处理片段
            fragments = self.hippocampus.get_short_term_fragments()
            results["steps"]["hippocampus"] = {
                "fragments_count": len(fragments),
                "status": "completed"
            }

            if not fragments:
                results["status"] = "completed"
                results["message"] = "没有需要处理的片段"
                return results

            if self.config.get("debug", False):
                print(f"[SEARCH] 开始记忆巩固，处理{len(fragments)}个片段")

            # 步骤2: 检察官初级筛选
            primary_approved, invalid_fragments = self.prosecutor.primary_screening(fragments)
            self.prosecutor.save_primary_approved(primary_approved)
            self.prosecutor.archive_invalid_fragments(invalid_fragments)

            results["steps"]["prosecutor_primary"] = {
                "primary_approved": len(primary_approved),
                "invalid_fragments": len(invalid_fragments),
                "status": "completed"
            }

            if not primary_approved:
                results["status"] = "completed"
                results["message"] = "没有片段通过初级筛选"
                # 清理海马体中的已处理片段
                fragment_ids = [f["fragment_id"] for f in fragments]
                self.hippocampus.clear_processed_fragments(fragment_ids)
                return results

            # 步骤3: 丘脑前部用户交互
            if self.config.get("auto_auth_disabled", True):
                # 需要用户确认
                formatted_data = self.thalamus.format_fragments_for_interaction(primary_approved)
                file_path, fragment_ids = self.thalamus.save_interaction_file(formatted_data)

                results["steps"]["thalamus_interaction"] = {
                    "interaction_file": str(file_path) if file_path else None,
                    "fragments_count": len(primary_approved),
                    "status": "awaiting_user_feedback",
                    "message": "请查看生成的交互文件并填写反馈"
                }

                results["status"] = "awaiting_user_feedback"
                results["interaction_file"] = str(file_path) if file_path else None

            else:
                # 自动认证模式（需要配置启用）
                # 这里简化处理：自动保留所有初级认证片段
                auto_feedback = {
                    "session_id": self.current_session_id,
                    "fragment_decisions": [
                        {"fragment_id": f["fragment_id"], "decision": "keep"}
                        for f in primary_approved
                    ],
                    "user_notes": "自动认证模式"
                }

                final_approved, to_delete, to_later = self.prosecutor.process_user_feedback(auto_feedback)

                results["steps"]["thalamus_interaction"] = {
                    "auto_auth": True,
                    "final_approved": len(final_approved),
                    "status": "completed"
                }

                # 继续到步骤4
                return self._complete_consolidation_with_feedback(auto_feedback, results)

            return results

        except Exception as e:
            return {"status": "error", "message": f"记忆巩固失败: {str(e)}"}

    def _complete_consolidation_with_feedback(self, feedback_data: Dict, partial_results: Dict) -> Dict:
        """使用用户反馈完成记忆巩固"""
        try:
            results = partial_results

            # 步骤4: 检察官二次认证
            final_approved, to_delete, to_later = self.prosecutor.process_user_feedback(feedback_data)

            results["steps"]["prosecutor_secondary"] = {
                "final_approved": len(final_approved),
                "user_deleted": len(to_delete),
                "pending_later": len(to_later),
                "status": "completed"
            }

            # 步骤5: 大脑皮层永久存储
            storage_results = []
            for fragment in final_approved:
                success, message = self.cortex.verify_and_store(fragment)
                storage_results.append({
                    "fragment_id": fragment["fragment_id"],
                    "success": success,
                    "message": message
                })

            results["steps"]["cortex_storage"] = {
                "stored_count": sum(1 for r in storage_results if r["success"]),
                "failed_count": sum(1 for r in storage_results if not r["success"]),
                "details": storage_results,
                "status": "completed"
            }

            # 步骤6: 清理海马体中的已处理片段
            all_fragment_ids = [
                f["fragment_id"] for f in final_approved + to_delete
            ]
            self.hippocampus.clear_processed_fragments(all_fragment_ids)

            # 对于pending_later的片段，保持在海马体中
            later_fragment_ids = [f["fragment_id"] for f in to_later]
            results["pending_later_fragments"] = later_fragment_ids

            results["status"] = "completed"
            results["message"] = f"记忆巩固完成: 存储{len(final_approved)}个, 删除{len(to_delete)}个"

            if self.config.get("debug", False):
                print(f"[OK] 记忆巩固完成: 永久存储{len(final_approved)}个片段")

            return results

        except Exception as e:
            return {"status": "error", "message": f"完成巩固失败: {str(e)}"}

    def process_user_feedback_file(self, feedback_file_path: str) -> Dict:
        """处理用户反馈文件"""
        if not all([self.prosecutor, self.thalamus, self.cortex, self.hippocampus]):
            return {"status": "error", "message": "Agent未完全初始化"}

        try:
            feedback_file = Path(feedback_file_path)
            if not feedback_file.exists():
                return {"status": "error", "message": "反馈文件不存在"}

            # 丘脑前部解析反馈
            feedback_data = self.thalamus.process_feedback_from_file(feedback_file)

            if feedback_data.get("status") == "error":
                return feedback_data

            # 完成记忆巩固
            results = {
                "status": "processing_feedback",
                "timestamp": datetime.now().isoformat(),
                "feedback_data": feedback_data
            }

            return self._complete_consolidation_with_feedback(feedback_data, results)

        except Exception as e:
            return {"status": "error", "message": f"处理反馈文件失败: {str(e)}"}

    def retrieve_and_inject_memories(self, user_input: str, context_tokens_remaining: int) -> Tuple[str, List[Dict]]:
        """检索并注入相关记忆

        Returns:
            (injection_text, fragments_used)
        """
        if not self.cortex:
            return "", []

        try:
            # 检索相关记忆
            related_fragments = self.cortex.retrieve_related_memories(
                user_input, context_tokens_remaining
            )

            if not related_fragments:
                return "", []

            # 格式化为注入文本
            injection_text = self.cortex.format_memories_for_injection(related_fragments)

            if self.config.get("debug", False):
                print(f"[BRAIN] 注入{len(related_fragments)}个相关记忆片段")

            return injection_text, related_fragments

        except Exception as e:
            print(f"检索记忆失败: {e}")
            return "", []

    def get_system_status(self) -> Dict:
        """获取系统状态"""
        status = {
            "is_running": self.is_running,
            "current_session_id": self.current_session_id,
            "config": {
                "enabled": self.config.get("enabled", True),
                "token_threshold": self.config.get("token_threshold"),
                "score_threshold": self.config.get("score_threshold")
            }
        }

        # 获取各Agent状态
        if self.hippocampus:
            session_info = self.hippocampus.get_session_info()
            status["hippocampus"] = session_info

        if self.prosecutor:
            stats = self.prosecutor.get_stats()
            status["prosecutor"] = stats

        if self.thalamus:
            interaction_status = self.thalamus.get_interaction_status()
            status["thalamus"] = interaction_status

        if self.cortex:
            stats = self.cortex.get_stats()
            status["cortex"] = stats

        return status

    def end_session(self):
        """结束当前会话"""
        if self.hippocampus:
            self.hippocampus.end_session()

        self.current_session_id = None
        self.is_running = False

        if self.config.get("debug", False):
            print("[STOP] 记忆管理会话结束")

    def maintenance_tasks(self):
        """执行维护任务"""
        tasks_executed = []

        try:
            # 检查超时的交互
            if self.thalamus:
                timeout_result = self.thalamus.check_timeout_fragments()
                if timeout_result.get("timeout_interactions"):
                    tasks_executed.append({
                        "task": "check_timeout_fragments",
                        "result": timeout_result
                    })

            # 清理非活跃片段
            if self.cortex:
                archived_count = self.cortex.cleanup_inactive_fragments(days_inactive=180)
                if archived_count > 0:
                    tasks_executed.append({
                        "task": "cleanup_inactive_fragments",
                        "archived_count": archived_count
                    })

            # 创建备份（按频率）
            if self.cortex:
                last_backup_file = self.data_dir / ".last_backup"
                backup_frequency = self.config.get("backup_frequency_days", 1)

                should_backup = False
                if not last_backup_file.exists():
                    should_backup = True
                else:
                    try:
                        with open(last_backup_file, 'r') as f:
                            last_backup_time = datetime.fromisoformat(f.read().strip())
                        days_since_backup = (datetime.now() - last_backup_time).days
                        should_backup = days_since_backup >= backup_frequency
                    except:
                        should_backup = True

                if should_backup:
                    backup_path = self.cortex.create_backup()
                    tasks_executed.append({
                        "task": "create_backup",
                        "backup_path": backup_path
                    })
                    with open(last_backup_file, 'w') as f:
                        f.write(datetime.now().isoformat())

            # 清理旧文件
            if self.thalamus:
                self.thalamus.cleanup_old_files(days_old=7)
                tasks_executed.append({
                    "task": "cleanup_old_files",
                    "days_old": 7
                })

            return {
                "status": "completed",
                "tasks_executed": tasks_executed,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "tasks_executed": tasks_executed
            }

    def export_memories(self, format: str = "json", topic_filter: str = None) -> str:
        """导出记忆"""
        if not self.cortex:
            return None

        try:
            return self.cortex.export_memories(format, topic_filter)
        except Exception as e:
            print(f"导出记忆失败: {e}")
            return None

    def create_backup(self, backup_name: str = None) -> str:
        """创建备份"""
        if not self.cortex:
            return None

        try:
            return self.cortex.create_backup(backup_name)
        except Exception as e:
            print(f"创建备份失败: {e}")
            return None


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
        print(f"[OK] 创建默认配置文件: {config_file}")

    return config_file


# 简单的命令行接口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="记忆管理系统协调器")
    parser.add_argument("--init", action="store_true", help="初始化系统")
    parser.add_argument("--status", action="store_true", help="查看系统状态")
    parser.add_argument("--export", choices=["json", "markdown"], help="导出记忆")
    parser.add_argument("--backup", action="store_true", help="创建备份")
    parser.add_argument("--maintenance", action="store_true", help="执行维护任务")
    parser.add_argument("--test", action="store_true", help="运行测试")

    args = parser.parse_args()

    if args.init:
        # 创建默认配置
        config_file = create_default_config()
        print(f"初始化完成，配置文件: {config_file}")

    elif args.status:
        coordinator = MemoryCoordinator()
        status = coordinator.get_system_status()
        print(json.dumps(status, ensure_ascii=False, indent=2))

    elif args.export:
        coordinator = MemoryCoordinator()
        export_path = coordinator.export_memories(format=args.export)
        if export_path:
            print(f"导出完成: {export_path}")
        else:
            print("导出失败")

    elif args.backup:
        coordinator = MemoryCoordinator()
        backup_path = coordinator.create_backup()
        if backup_path:
            print(f"备份完成: {backup_path}")
        else:
            print("备份失败")

    elif args.maintenance:
        coordinator = MemoryCoordinator()
        result = coordinator.maintenance_tasks()
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.test:
        print("[TEST] 运行集成测试...")

        # 创建测试目录
        test_dir = Path("test_coordinator")
        if test_dir.exists():
            import shutil
            shutil.rmtree(test_dir)
        test_dir.mkdir()

        # 初始化协调器
        coordinator = MemoryCoordinator(str(test_dir))
        coordinator.start_session("test_session")

        # 测试记录对话
        print("\n[RECORD] 测试记录对话...")
        result = coordinator.record_conversation_turn(
            "我需要开发一个Python API服务器",
            "好的，建议使用FastAPI框架，它性能好且易于使用。"
        )
        print(f"记录结果: {result}")

        # 测试状态查询
        print("\n[STATUS] 测试状态查询...")
        status = coordinator.get_system_status()
        print(f"系统状态: {status.get('is_running')}")

        # 测试记忆检索
        print("\n[SEARCH] 测试记忆检索...")
        injection_text, fragments = coordinator.retrieve_and_inject_memories(
            "Python API开发", 1000
        )
        print(f"检索到{len(fragments)}个片段")
        if injection_text:
            print(f"注入文本长度: {len(injection_text)}")

        print("\n[OK] 集成测试完成")
        print(f"测试目录: {test_dir}")

    else:
        parser.print_help()