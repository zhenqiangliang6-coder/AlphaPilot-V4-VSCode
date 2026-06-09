// src/components/IntentBadge.tsx
import React from 'react';

interface IntentBadgeProps {
  intent?: string;
}

// ⭐ v2.6: 意图配置映射表
const INTENT_CONFIG: Record<string, { label: string; icon: string; color: string }> = {
  write_code: { label: '代码生成', icon: '💻', color: 'blue' },
  explain_code: { label: '代码解释', icon: '📖', color: 'green' },
  fix_code: { label: '错误修复', icon: '🔧', color: 'red' },
  creative_writing: { label: '创意写作', icon: '✨', color: 'purple' },
  chat: { label: '闲聊对话', icon: '💬', color: 'gray' },
  analysis: { label: '需求分析', icon: '🔍', color: 'yellow' },
  architecture: { label: '架构设计', icon: '🏗️', color: 'indigo' },
  refactor: { label: '代码重构', icon: '♻️', color: 'teal' },
  generate_doc: { label: '文档生成', icon: '📝', color: 'orange' },
  profile: { label: '性能分析', icon: '⚡', color: 'pink' }
};

export const IntentBadge: React.FC<IntentBadgeProps> = ({ intent }) => {
  if (!intent) return null;

  const config = INTENT_CONFIG[intent];
  if (!config) return null;

  // 动态生成 Tailwind 类名
  const bgColorClass = `bg-${config.color}-500/20`;
  const textColorClass = `text-${config.color}-400`;
  const borderColorClass = `border-${config.color}-500/30`;

  return (
    <span 
      className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full ${bgColorClass} ${textColorClass} border ${borderColorClass}`}
      title={config.label}
    >
      <span>{config.icon}</span>
      <span>{config.label}</span>
    </span>
  );
};
