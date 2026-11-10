import React, { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import mermaid from 'mermaid';

interface MermaidBlockProps {
  code: string;
  label?: string;
}

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
      tertiaryTextColor: '#e2e8f0',
      edgeLabelBackground: 'rgba(15, 23, 42, 0.92)',
      fontSize: '14px',
    },
    flowchart: {
      useMaxWidth: true,
      htmlLabels: true,
      curve: 'basis',
    },
  });
  _mermaidReady = true;
}

function injectEdgeLabelStyles(svg: string): string {
  const styleTag = `
<style>
  .edgeLabel rect {
    fill: rgba(15, 23, 42, 0.92) !important;
    stroke: rgba(148, 163, 184, 0.35) !important;
    stroke-width: 1px !important;
    rx: 4px !important;
  }
  .edgeLabel span, .edgeLabel p, .edgeLabel text, .edgeLabel tspan, .edgeLabel foreignObject {
    color: #e2e8f0 !important;
    fill: #e2e8f0 !important;
    font-size: 13px !important;
    font-weight: 500 !important;
  }
  .label foreignObject, .label div, .label span {
    color: #e2e8f0 !important;
  }
</style>`;
  if (svg.includes('</svg>')) {
    return svg.replace('</svg>', styleTag + '\n</svg>');
  }
  return styleTag + svg;
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

  sanitized = sanitized.replace(/<br\s*\/?>/gi, '#lt;br/#gt;');

  return sanitized;
}

const MIN_SCALE = 0.25;
const MAX_SCALE = 3.0;
const SCALE_STEP = 0.1;

export const MermaidBlock: React.FC<MermaidBlockProps> = ({ code, label }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [svgContent, setSvgContent] = useState<string | null>(null);
  const [scale, setScale] = useState(1);

  const sanitizedCode = useMemo(() => sanitizeMermaidCode(code), [code]);

  const zoomIn = useCallback(() => setScale((s) => Math.min(MAX_SCALE, +(s + SCALE_STEP).toFixed(2))), []);
  const zoomOut = useCallback(() => setScale((s) => Math.max(MIN_SCALE, +(s - SCALE_STEP).toFixed(2))), []);
  const zoomReset = useCallback(() => setScale(1), []);

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      if (e.deltaY < 0) zoomIn();
      else zoomOut();
    }
  }, [zoomIn, zoomOut]);

  useEffect(() => {
    let cancelled = false;

    const renderDiagram = async () => {
      try {
        ensureMermaidInit();

        const id = `mermaid-${Math.random().toString(36).substr(2, 9)}`;
        const { svg } = await mermaid.render(id, sanitizedCode);

        if (!cancelled) {
          setSvgContent(injectEdgeLabelStyles(svg));
          setError(null);
          setScale(1);
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
    <div className="my-4 rounded-lg border border-blue-500/20 bg-gray-900/30">
      <div className="flex items-center justify-between px-4 py-2 border-b border-blue-500/10">
        {label ? (
          <span className="text-xs text-blue-400 font-semibold">{label}</span>
        ) : (
          <span className="text-xs text-gray-500">结构图</span>
        )}
        <div className="flex items-center gap-1">
          <button
            onClick={zoomOut}
            disabled={scale <= MIN_SCALE}
            title="缩小 (Ctrl+滚轮)"
            className="px-1.5 py-0.5 text-xs text-gray-400 hover:text-gray-200 bg-gray-800/60 hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >−</button>
          <button
            onClick={zoomReset}
            title="重置缩放"
            className="px-2 py-0.5 text-xs text-gray-400 hover:text-gray-200 bg-gray-800/60 hover:bg-gray-700 rounded transition-colors"
          >{Math.round(scale * 100)}%</button>
          <button
            onClick={zoomIn}
            disabled={scale >= MAX_SCALE}
            title="放大 (Ctrl+滚轮)"
            className="px-1.5 py-0.5 text-xs text-gray-400 hover:text-gray-200 bg-gray-800/60 hover:bg-gray-700 rounded disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >+</button>
        </div>
      </div>
      <div
        className="overflow-auto p-4 flex justify-center"
        style={{ maxHeight: '65vh' }}
        onWheel={handleWheel}
      >
        <div
          ref={containerRef}
          className="mermaid-container"
          style={{
            transform: `scale(${scale})`,
            transformOrigin: 'top center',
            transition: 'transform 0.15s ease-out',
          }}
          dangerouslySetInnerHTML={{ __html: svgContent }}
        />
      </div>
      <details className="border-t border-blue-500/10">
        <summary className="px-4 py-1.5 text-xs text-gray-500 cursor-pointer hover:text-gray-400 select-none">
          Mermaid 源码
        </summary>
        <pre className="mx-4 mb-3 text-xs text-gray-400 whitespace-pre-wrap overflow-x-auto bg-gray-900/50 p-3 rounded max-h-48 overflow-y-auto">
          {code}
        </pre>
      </details>
    </div>
  );
};