// src/components/PersonaIcon.tsx
import React from 'react';

interface PersonaIconProps {
  persona?: string;
}

// ⭐ v2.6: 人格配置映射表
const PERSONA_CONFIG: Record<string, { name: string; icon: string; gradient: string }> = {
  engineer: { 
    name: '工程师', 
    icon: '👨‍💻', 
    gradient: 'from-blue-500 to-cyan-500' 
  },
  creator: { 
    name: '创作者', 
    icon: '🎨', 
    gradient: 'from-purple-500 to-pink-500' 
  },
  conversational: { 
    name: '对话', 
    icon: '💬', 
    gradient: 'from-green-500 to-emerald-500' 
  }
};

export const PersonaIcon: React.FC<PersonaIconProps> = ({ persona }) => {
  if (!persona) return null;

  const config = PERSONA_CONFIG[persona];
  if (!config) return null;

  return (
    <div 
      className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-gradient-to-r ${config.gradient} text-white text-xs font-medium shadow-md hover:shadow-lg transition-shadow cursor-default`}
      title={`${config.name}人格`}
    >
      <span className="text-sm">{config.icon}</span>
      <span>{config.name}</span>
    </div>
  );
};
