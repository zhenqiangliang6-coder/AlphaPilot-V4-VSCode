/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        vscode: {
          'bg': 'var(--vscode-editor-background)',
          'fg': 'var(--vscode-editor-foreground)',
          'border': 'var(--vscode-panel-border)',
          'button-bg': 'var(--vscode-button-background)',
          'button-fg': 'var(--vscode-button-foreground)',
          'input-bg': 'var(--vscode-input-background)',
          'input-fg': 'var(--vscode-input-foreground)',
          'list-hover': 'var(--vscode-list-hoverBackground)',
          'accent': 'var(--vscode-textLink-foreground)',
        }
      }
    },
  },
  plugins: [],
}
