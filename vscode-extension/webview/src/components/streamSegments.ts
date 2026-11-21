// src/components/streamSegments.ts
// 流式分段器（围栏代码块解析状态机）— 从 EnhancedStreamingOutput 抽取为独立模块
// 抽取动机：
//   1. 契约测试（streamSegments.test.ts）直接锁死解析行为，不拖 Prism/Mermaid 等重依赖
//   2. 解析逻辑与渲染分离：状态机的输入输出契约一目了然

export interface ContentSegment {
  type: 'text' | 'code_block';
  content: string;
  language: string;
  isComplete: boolean; // 代码块是否已闭合 ```
}

/**
 * 把流式累积的 markdown 原文切成 text / code_block 分段。
 * - 代码块未闭合时（流式中）标记 isComplete=false，尾部自然吞到 $
 * - 已稳定的前缀分段逐字节不变（memo 化渲染的前提）
 * - 语言标记统一小写（Prism 语言查找依赖）
 */
export function parseContentSegments(text: string): ContentSegment[] {
  const segments: ContentSegment[] = [];
  const regex = /```(\w*)\n([\s\S]*?)(```|$)/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      segments.push({
        type: 'text',
        content: text.substring(lastIndex, match.index),
        language: '',
        isComplete: true,
      });
    }
    segments.push({
      type: 'code_block',
      content: match[2] || '',
      language: (match[1] || '').toLowerCase(),
      isComplete: match[3] === '```',
    });
    lastIndex = match.index + match[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({
      type: 'text',
      content: text.substring(lastIndex),
      language: '',
      isComplete: true,
    });
  }

  return segments;
}
