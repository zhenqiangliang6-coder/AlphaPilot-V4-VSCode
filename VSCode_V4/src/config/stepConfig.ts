// src/config/stepConfig.ts
// step_executor 步骤类型配置

import { StepType } from '../types/task';

export interface StepConfig {
  name: string;
  icon: string;
  color: string;
  description: string;
}

export const STEP_CONFIG: Record<StepType, StepConfig> = {
  analyze: {
    name: '需求分析',
    icon: '🔍',
    color: '#4fc3f7',
    description: '分析用户需求和上下文'
  },
  plan: {
    name: '步骤规划',
    icon: '📋',
    color: '#81c784',
    description: '制定详细的执行计划'
  },
  write: {
    name: '代码编写',
    icon: '✏️',
    color: '#ffb74d',
    description: '生成代码实现'
  },
  refine: {
    name: '优化改进',
    icon: '💎',
    color: '#e57373',
    description: '优化和改进代码质量'
  },
  test: {
    name: '测试验证',
    icon: '✅',
    color: '#ba68c8',
    description: '运行测试确保正确性'
  },
  fix: {
    name: '错误修复',
    icon: '🔧',
    color: '#ff8a65',
    description: '修复发现的问题'
  },
  profile: {
    name: '性能分析',
    icon: '⚡',
    color: '#4db6ac',
    description: '分析和优化性能'
  },
  doc: {
    name: '文档生成',
    icon: '📝',
    color: '#7986cb',
    description: '生成文档和注释'
  }
};

export function getStepConfig(type: StepType): StepConfig {
  return STEP_CONFIG[type] || {
    name: '未知步骤',
    icon: '❓',
    color: '#999999',
    description: '未知的步骤类型'
  };
}

export function getStepIcon(type: StepType): string {
  return STEP_CONFIG[type]?.icon || '❓';
}

export function getStepName(type: StepType): string {
  return STEP_CONFIG[type]?.name || '未知步骤';
}
