// src/components/streamSegments.test.ts
// 契约测试：流式分段器 parseContentSegments（围栏代码块解析状态机）
// 锁定：分段结构 / 未闭合跨 chunk 识别 / 闭合判定 / 语言归一化 / 增量到达时前缀段稳定

import { describe, it, expect } from 'vitest';
import { parseContentSegments } from './streamSegments';

describe('parseContentSegments 契约', () => {
  it('空字符串：零分段', () => {
    expect(parseContentSegments('')).toEqual([]);
  });

  it('纯文本：单 text 段', () => {
    expect(parseContentSegments('只有文字')).toEqual([
      { type: 'text', content: '只有文字', language: '', isComplete: true },
    ]);
  });

  it('完整闭合代码块：前文 / 代码 / 后文 三段', () => {
    const segs = parseContentSegments('前文\n```js\ncode()\n```\n后文');
    expect(segs).toEqual([
      { type: 'text', content: '前文\n', language: '', isComplete: true },
      { type: 'code_block', content: 'code()\n', language: 'js', isComplete: true },
      { type: 'text', content: '\n后文', language: '', isComplete: true },
    ]);
  });

  it('跨 chunk 未闭合代码块（流式中）：识别为 isComplete=false 的尾段', () => {
    // 模拟 chunk 陆续到达：'看这段\n```python\nimport os' 尚未闭合
    const partial = '看这段\n```python\nimport os';
    expect(parseContentSegments(partial)).toEqual([
      { type: 'text', content: '看这段\n', language: '', isComplete: true },
      { type: 'code_block', content: 'import os', language: 'python', isComplete: false },
    ]);
  });

  it('跨 chunk 闭合：拼接后同一代码块翻转为 isComplete=true', () => {
    const chunk1 = '分析如下\n```js\ncon';        // 未闭合
    const chunk2 = 'sole.log(1)\n```\n完毕';        // 闭合 + 尾文

    const before = parseContentSegments(chunk1);
    const after = parseContentSegments(chunk1 + chunk2);

    // 未闭合态
    expect(before[1].isComplete).toBe(false);
    // 拼接后闭合
    expect(after).toEqual([
      { type: 'text', content: '分析如下\n', language: '', isComplete: true },
      { type: 'code_block', content: 'console.log(1)\n', language: 'js', isComplete: true },
      { type: 'text', content: '\n完毕', language: '', isComplete: true },
    ]);
  });

  it('增量到达：新 chunk 只影响尾段，前缀段逐字节稳定（memo 化的前提）', () => {
    const partial = '标题\n```ts\nconst a = 1;';
    const extended = partial + '\nconst b = 2;';

    const before = parseContentSegments(partial);
    const after = parseContentSegments(extended);

    // 前缀段（text 段）不变
    expect(after[0]).toEqual(before[0]);
    // 尾段仍为未闭合代码块，内容按追加增长
    expect(after[1].isComplete).toBe(false);
    expect(after[1].content.startsWith(before[1].content)).toBe(true);
    expect(after[1].content).toBe('const a = 1;\nconst b = 2;');
  });

  it('mermaid 识别：language=mermaid 透传', () => {
    const segs = parseContentSegments('```mermaid\ngraph TD\nA-->B\n```');
    expect(segs[0].type).toBe('code_block');
    expect(segs[0].language).toBe('mermaid');
    expect(segs[0].isComplete).toBe(true);
  });

  it('语言归一化：大写语言标记转小写（Prism 查找依赖）', () => {
    const segs = parseContentSegments('```PYTHON\nx = 1\n```');
    expect(segs[0].language).toBe('python');
  });

  it('连续代码块：中间无文本时产出两段 code_block，无空 text 段', () => {
    const segs = parseContentSegments('```js\na()\n``````py\nb()\n```');
    expect(segs).toHaveLength(2);
    expect(segs.every((s) => s.type === 'code_block')).toBe(true);
    expect(segs[0]).toMatchObject({ language: 'js', isComplete: true });
    expect(segs[1]).toMatchObject({ language: 'py', isComplete: true });
  });
});
