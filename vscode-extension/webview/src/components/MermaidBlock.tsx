import React, { useEffect, useRef, useState, useMemo } from 'react';
import mermaid from 'mermaid';

interface MermaidBlockProps {
  code: string;
  label?: string;
}

const MERMAID_INITIALIZED = Symbol('mermaid_initialized');

let _mermaidReady = false;

function ensureMermaidInit() {
  if (_mermaidReady) return;
  mermaid.initialize({
    startOnLoad: false,
    theme: 'dark',
    suppressErrorRendering: true,
    themeVariables: {
      primaryColor: '#3b82f6',
      primaryTextColor: '#e2e8f0',
      primaryBorderColor: '#60a5fa',
      lineColor: '#94a3b8',
      secondaryColor: '#1e293b',
      tertiaryColor: '#334155',
    },
    flowchart: {
      useMaxWidth: true,
      htmlLabels: true,
      curve: 'basis',
    },
  });
  _mermaidReady = true;
}

function sanitizeMermaidCode(code: string): string {
  let sanitized = code;

  sanitized = sanitized.replace(
    /(\[[^\]]*\[[^\]]*\][^\]]*\])/g,
    (_match: string) => {
      const inner = _match.slice(1, -1);
      return '["' + inner.replace(/"/g, '\\"') + '"]';
    }
  );

  sanitized = sanitized.replace(/[\u{1F600}-\u{1F9FF}\u{2600}-\u{27BF}\u{2702}-\u{27B0}]/gu, '');

  sanitized = sanitized.replace(/(\w+)\.(\w+)/g, (_match: string) => {
    const knownModules = ['python_worker', 'vscode_extension', 'node_api', 'src', 'tests'];
    const parts = _match.split('.');
    if (knownModules.includes(parts[0])) {
      return _match;
    }
    return _match;
  });

  sanitized = sanitized.replace(/<br\s*\/?>/gi, '#lt;br/#gt;');

  return sanitized;
}

export const MermaidBlock: React.FC<MermaidBlockProps> = ({ code, label }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);

  const sanitizedCode = useMemo(() => sanitizeMermaidCode(code), [code]);

  useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      try {
        ensureMermaidInit();

        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, sanitizedCode);

        if (!cancelled) {
          setSvgContent(svg);
          setError(null);
        }
      } catch (err: any) {
        if (!cancelled) {
          console.error('[MermaidBlock] 渲染失败, code 前200字符:', sanitizedCode.substring(0, 200));
          console.error('[MermaidBlock] 错误:', err.message || err);

          setError(err.message || 'Mermaid 渲染失败');
          setSvgContent(null);
        }
      }
    };

    renderDiagram();

    return () => {
      cancelled = true;
    };
  }, [sanitizedCode]);

  if (error) {
    return (
      <div className="my-4 rounded-lg border border-red-500/30 bg-red-500/5 p-4">
        <div className="flex items-center gap-2 mb-2 text-red-400 text-xs font-semibold">
          <span>⚠️</span>
          <span>Mermaid 渲染失败（原始数据已保留，可手动查看）</span>
        </div>
        <pre className="text-xs text-red-300/80 whitespace-pre-wrap overflow-x-auto">
          {error}
        </pre>
        <details className="mt-2">
          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
            查看原始 Mermaid 源码
          </summary>
          <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto bg-gray-900/50 p-3 rounded">
            {code}
          </pre>
        </details>
        <details className="mt-1">
          <summary className="text-xs text-gray-400 cursor-pointer hover:text-gray-300">
            查看清洗后的 Mermaid 源码
          </summary>
          <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto bg-gray-900/50 p-3 rounded">
            {sanitizedCode}
          </pre>
        </details>
      </div>
    );
  }

  if (!svgContent) {
    return (
      <div className="my-4 rounded-lg border border-blue-500/20 bg-blue-500/5 p-4 flex items-center justify-center">
        <div className="animate-pulse text-gray-400 text-sm">正在渲染结构图...</div>
      </div>
    );
  }

  return (
    <div className="my-4 rounded-lg border border-blue-500/20 bg-gray-900/30 p-4 overflow-x-auto">
      {label && (
        <div className="flex items-center gap-2 mb-3 text-xs text-blue-400 font-semibold">
          <span>  </span>
          <span>{label}</span>
        </div>
      )}
      <div
        ref={containerRef}
        className="mermaid-container flex justify-center"
        dangerouslySetInnerHTML={{ __html: svgContent }}
      />
      <details className="mt-3 border-t border-gray-700 pt-2">
        <summary className="text-xs text-gray-500 cursor-pointer hover:text-gray-400 select-none">
          Mermaid 源码
        </summary>
        <pre className="mt-2 text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto bg-gray-900/50 p-3 rounded max-h-48 overflow-y-auto">
          {code}
        </pre>
      </details>
    </div>
  );
};