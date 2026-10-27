// src/components/MarkdownRenderer.tsx
import React, { useState, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { MermaidBlock } from './MermaidBlock';

interface MarkdownRendererProps {
  content: string;
}

function normalizeMarkdownTables(text: string): string {
  const lines = text.split('\n');
  const result: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (!line.includes('|---') || line.startsWith('```')) {
      result.push(line);
      continue;
    }

    const cells = line.split('|').map(c => c.trim());
    if (cells.length > 0 && cells[0] === '') cells.shift();
    if (cells.length > 0 && cells[cells.length - 1] === '') cells.pop();

    const sepStart = cells.findIndex(c => /^-{3,}$/.test(c));
    if (sepStart <= 0) {
      result.push(line);
      continue;
    }

    // Count consecutive --- cells to get numCols
    let sepEnd = sepStart;
    while (sepEnd < cells.length && /^-{3,}$/.test(cells[sepEnd])) {
      sepEnd++;
    }
    const numCols = sepEnd - sepStart;
    if (numCols === 0) {
      result.push(line);
      continue;
    }

    // Header: cells before separator, excluding trailing empties
    let headerEnd = sepStart;
    while (headerEnd > 0 && cells[headerEnd - 1] === '') {
      headerEnd--;
    }
    const headerCells = cells.slice(0, headerEnd);

    // Data: cells after separator, excluding leading empties
    let dataStart = sepEnd;
    while (dataStart < cells.length && cells[dataStart] === '') {
      dataStart++;
    }
    const rawData = cells.slice(dataStart);

    // Filter empty boundary cells between data rows (artifact of | | between rows)
    const dataCells: string[] = [];
    for (let j = 0; j < rawData.length; j++) {
      if (j > 0 && j % numCols === 0 && rawData[j] === '') continue;
      dataCells.push(rawData[j]);
    }

    const headerRow = '| ' + headerCells.join(' | ') + ' |';
    const sepRow = '|' + Array(numCols).fill('---').join('|') + '|';
    result.push(headerRow);
    result.push(sepRow);

    for (let j = 0; j < dataCells.length; j += numCols) {
      const rowCells = dataCells.slice(j, j + numCols);
      result.push('| ' + rowCells.join(' | ') + ' |');
    }
  }

  return result.join('\n');
}

export const MarkdownRenderer: React.FC<MarkdownRendererProps> = ({ content }) => {
  const [copiedCodeId, setCopiedCodeId] = useState<string | null>(null);

  const normalizedContent = useMemo(() => normalizeMarkdownTables(content), [content]);

  const handleCopyCode = (code: string, id: string) => {
    navigator.clipboard.writeText(code).then(() => {
      setCopiedCodeId(id);
      setTimeout(() => setCopiedCodeId(null), 2000);
    });
  };

  return (
    <div className="markdown-renderer prose prose-invert max-w-none">
      <ReactMarkdown
        components={{
          code({ node, inline, className, children, ...props }: any) {
            const match = /language-(\w+)/.exec(className || '');
            const codeString = String(children).replace(/\n$/, '');
            const codeId = `code-${Math.random().toString(36).substr(2, 9)}`;

            if (!inline && match) {
              const language = match[1];

              if (language === 'mermaid') {
                return <MermaidBlock code={codeString} />;
              }

              return (
                <div className="relative group my-4">
                  <button
                    onClick={() => handleCopyCode(codeString, codeId)}
                    className="absolute top-2 right-2 px-2 py-1 text-xs bg-vscode-button-bg/80 hover:bg-vscode-button-bg text-vscode-button-fg rounded opacity-0 group-hover:opacity-100 transition-opacity"
                    title="复制代码"
                  >
                    {copiedCodeId === codeId ? '✓ 已复制' : '📋 复制'}
                  </button>

                  <SyntaxHighlighter
                    style={vscDarkPlus}
                    language={match[1]}
                    PreTag="div"
                    {...props}
                  >
                    {codeString}
                  </SyntaxHighlighter>
                </div>
              );
            }

            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          pre({ children }) {
            return <>{children}</>;
          },
          table({ children }) {
            return (
              <div className="overflow-x-auto my-4 rounded-lg border border-gray-700/30">
                <table className="min-w-full border-collapse text-xs">
                  {children}
                </table>
              </div>
            );
          },
          thead({ children }) {
            return (
              <thead className="bg-gray-800/60 [&_th]:border-b [&_th]:border-gray-600/30">
                {children}
              </thead>
            );
          },
          tbody({ children }) {
            return <tbody>{children}</tbody>;
          },
          tr({ children, ...props }: any) {
            const isEven = props['data-index'] !== undefined && props['data-index'] % 2 === 0;
            return (
              <tr className={`${isEven ? 'bg-gray-800/20' : ''} hover:bg-gray-700/20 transition-colors`}>
                {children}
              </tr>
            );
          },
          th({ children }) {
            return (
              <th className="px-3 py-2 text-left font-semibold text-gray-300 whitespace-nowrap">
                {children}
              </th>
            );
          },
          td({ children }) {
            return (
              <td className="px-3 py-2 border-t border-gray-700/20 text-gray-400">
                {children}
              </td>
            );
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
};