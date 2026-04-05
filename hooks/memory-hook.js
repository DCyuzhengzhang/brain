#!/usr/bin/env node
/**
 * Claude Code Memory Management Hook
 * 在每轮对话后自动调用记忆管理系统
 */

const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// 配置
const PLUGIN_DIR = path.join(__dirname, '..');
const DATA_DIR = path.join(PLUGIN_DIR, 'data');
const PYTHON_PATH = process.platform === 'win32' ? 'python' : 'python3';

class MemoryHook {
  constructor() {
    this.coordinator = null;
    this.config = this.loadConfig();
    this.sessionId = null;
  }

  loadConfig() {
    const configPath = path.join(DATA_DIR, 'config', 'config.json');
    try {
      if (fs.existsSync(configPath)) {
        return JSON.parse(fs.readFileSync(configPath, 'utf8'));
      }
    } catch (error) {
      console.error('加载配置失败:', error.message);
    }
    return {
      enabled: true,
      debug: false,
      token_threshold: 25000
    };
  }

  async handleToolResult(toolName, result, metadata) {
    // 只在Claude输出后记录对话
    if (toolName !== 'Claude' || !result || !metadata.userInput) {
      return;
    }

    if (!this.config.enabled) {
      return;
    }

    try {
      // 准备数据
      const userInput = metadata.userInput;
      const claudeOutput = result;

      // 调用Python记忆管理系统
      await this.callMemorySystem(userInput, claudeOutput);

    } catch (error) {
      console.error('处理记忆失败:', error.message);
    }
  }

  async callMemorySystem(userInput, claudeOutput) {
    return new Promise((resolve, reject) => {
      const scriptPath = path.join(PLUGIN_DIR, 'src', 'coordinator.py');

      // 转义输入中的特殊字符
      const escapedInput = userInput.replace(/"/g, '\\"').replace(/'/g, "\\'");
      const escapedOutput = claudeOutput.replace(/"/g, '\\"').replace(/'/g, "\\'");

      // 构建Python命令
      const pythonCode = `
import sys
import json
sys.path.append('${PLUGIN_DIR.replace(/\\/g, '\\\\')}/src')
from coordinator import MemoryCoordinator

coordinator = MemoryCoordinator()
result = coordinator.record_conversation_turn(
    ${JSON.stringify(escapedInput)},
    ${JSON.stringify(escapedOutput)}
)
print(json.dumps(result))
`;

      const pythonProcess = spawn(PYTHON_PATH, ['-c', pythonCode], {
        cwd: PLUGIN_DIR,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let output = '';
      let error = '';

      pythonProcess.stdout.on('data', (data) => {
        output += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        error += data.toString();
      });

      pythonProcess.on('close', (code) => {
        if (code === 0) {
          try {
            const result = JSON.parse(output);

            if (this.config.debug) {
              console.log('记忆记录结果:', result);
            }

            // 检查是否需要用户交互
            if (result.consolidation_triggered && result.interaction_file) {
              console.log('\n📝 记忆巩固触发!');
              console.log('请查看交互文件:', result.interaction_file);
              console.log('编辑文件后运行: python src/coordinator.py --process-feedback');
            }

            if (result.warning_message && this.config.debug) {
              console.log('⚠️', result.warning_message);
            }

            resolve(result);
          } catch (parseError) {
            reject(new Error(`解析结果失败: ${parseError.message}`));
          }
        } else {
          reject(new Error(`Python脚本失败 (${code}): ${error}`));
        }
      });

      pythonProcess.on('error', (error) => {
        reject(new Error(`启动Python进程失败: ${error.message}`));
      });
    });
  }

  async handleUserInput(input, metadata) {
    if (!this.config.enabled) {
      return null;
    }

    try {
      // 检查上下文剩余空间
      const remainingTokens = metadata.contextTokensRemaining || 4000;

      // 调用记忆检索
      return await this.retrieveMemories(input, remainingTokens);
    } catch (error) {
      console.error('检索记忆失败:', error.message);
      return null;
    }
  }

  async retrieveMemories(userInput, remainingTokens) {
    return new Promise((resolve, reject) => {
      const scriptPath = path.join(PLUGIN_DIR, 'src', 'coordinator.py');

      const pythonCode = `
import sys
import json
sys.path.append('${PLUGIN_DIR.replace(/\\/g, '\\\\')}/src')
from coordinator import MemoryCoordinator

coordinator = MemoryCoordinator()
injection_text, fragments = coordinator.retrieve_and_inject_memories(
    ${JSON.stringify(userInput)},
    ${remainingTokens}
)
result = {
    "injection_text": injection_text,
    "fragments_count": len(fragments)
}
print(json.dumps(result))
`;

      const pythonProcess = spawn(PYTHON_PATH, ['-c', pythonCode], {
        cwd: PLUGIN_DIR,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let output = '';
      let error = '';

      pythonProcess.stdout.on('data', (data) => {
        output += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        error += data.toString();
      });

      pythonProcess.on('close', (code) => {
        if (code === 0) {
          try {
            const result = JSON.parse(output);

            if (this.config.debug && result.fragments_count > 0) {
              console.log(`🧠 注入${result.fragments_count}个记忆片段`);
            }

            resolve(result.injection_text);
          } catch (parseError) {
            resolve(null); // 解析失败时不注入任何内容
          }
        } else {
          resolve(null); // 检索失败时不注入任何内容
        }
      });

      pythonProcess.on('error', (error) => {
        resolve(null); // 进程错误时不注入任何内容
      });
    });
  }

  async handleFeedbackProcessing(feedbackFile) {
    if (!fs.existsSync(feedbackFile)) {
      console.error('反馈文件不存在:', feedbackFile);
      return;
    }

    console.log('处理用户反馈:', feedbackFile);

    return new Promise((resolve, reject) => {
      const pythonCode = `
import sys
import json
sys.path.append('${PLUGIN_DIR.replace(/\\/g, '\\\\')}/src')
from coordinator import MemoryCoordinator

coordinator = MemoryCoordinator()
result = coordinator.process_user_feedback_file('${feedbackFile.replace(/\\/g, '\\\\')}')
print(json.dumps(result))
`;

      const pythonProcess = spawn(PYTHON_PATH, ['-c', pythonCode], {
        cwd: PLUGIN_DIR,
        stdio: ['pipe', 'pipe', 'pipe']
      });

      let output = '';
      let error = '';

      pythonProcess.stdout.on('data', (data) => {
        output += data.toString();
      });

      pythonProcess.stderr.on('data', (data) => {
        error += data.toString();
      });

      pythonProcess.on('close', (code) => {
        if (code === 0) {
          try {
            const result = JSON.parse(output);
            console.log('反馈处理完成:', result.message || result.status);
            resolve(result);
          } catch (parseError) {
            console.error('解析结果失败:', parseError.message);
            resolve({ status: 'error', message: parseError.message });
          }
        } else {
          console.error('处理失败:', error);
          resolve({ status: 'error', message: error });
        }
      });
    });
  }
}

// 导出hook类
module.exports = MemoryHook;

// 如果直接运行，提供命令行接口
if (require.main === module) {
  const hook = new MemoryHook();
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.log('记忆管理系统Hook');
    console.log('用法:');
    console.log('  node memory-hook.js record "用户输入" "Claude输出"');
    console.log('  node memory-hook.js retrieve "用户查询"');
    console.log('  node memory-hook.js process-feedback 文件路径');
    console.log('  node memory-hook.js status');
    process.exit(0);
  }

  const command = args[0];

  switch (command) {
    case 'record':
      if (args.length < 3) {
        console.error('需要用户输入和Claude输出参数');
        process.exit(1);
      }
      hook.callMemorySystem(args[1], args[2]).then(console.log).catch(console.error);
      break;

    case 'retrieve':
      if (args.length < 2) {
        console.error('需要用户查询参数');
        process.exit(1);
      }
      hook.retrieveMemories(args[1], 1000).then(console.log).catch(console.error);
      break;

    case 'process-feedback':
      if (args.length < 2) {
        console.error('需要反馈文件路径');
        process.exit(1);
      }
      hook.handleFeedbackProcessing(args[1]).then(console.log).catch(console.error);
      break;

    case 'status':
      console.log('配置:', hook.config);
      break;

    default:
      console.error('未知命令:', command);
      process.exit(1);
  }
}