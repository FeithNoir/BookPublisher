export interface Theme {
  id: string;
  name: string;
  description: string;
  defaults: {
    page_size: string;
    chapter_break: 'flow' | 'page' | 'recto';
    font_size: number;
    dropcaps: boolean;
    toc_depth?: number;
    [k: string]: unknown;
  };
  swatch: string[];
}

export interface ChapterInfo {
  index: number;
  label: string;
  title: string;
  words: number;
  numbered: boolean;
}

export interface DocumentOutline {
  id: string;
  name: string;
  title: string;
  meta: Record<string, string>;
  chapters: ChapterInfo[];
  words: number;
  images: number;
  parse_seconds: number;
  estimates: Record<string, number>;
}

export interface ExportOptions {
  theme: string;
  page_size: string | null;
  font_size: number | null;
  chapter_break: 'flow' | 'page' | 'recto' | null;
  dropcaps: boolean | null;
  hyphenate: boolean;
  toc: boolean;
  cover: boolean;
  title: string | null;
  author: string | null;
}

export interface PreviewPage {
  page: number;
  url: string;
  key: string;
}

export interface PreviewResult {
  pages: PreviewPage[];
  chunk_pages: number;
  first_page: number;
  seconds: number;
}

export interface JobSummary {
  id: string;
  kind: 'export' | 'import';
  title: string;
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled';
  files: string[];
  result: Record<string, any> | null;
  error: { message: string; chapter: string | null; detail: string } | null;
}

export type JobEvent =
  | { type: 'queued'; seq: number }
  | { type: 'plan'; seq: number; chunks: number; chapters: number; words: number; theme: string; titles: string[] }
  | { type: 'phase'; seq: number; phase: string; message: string; pending?: number; total?: number }
  | {
      type: 'chunk';
      seq: number;
      phase: string;
      index: number;
      done: number;
      total: number;
      pages: number;
      cached: boolean;
      words_done: number;
      words_total: number;
      eta_seconds: number | null;
      elapsed: number;
    }
  | { type: 'page'; seq: number; done: number; total: number }
  | { type: 'done'; seq: number; result: Record<string, any> }
  | { type: 'finished'; seq: number; result: Record<string, any> }
  | { type: 'error'; seq: number; message: string; chapter: string | null; detail: string }
  | { type: 'cancelled'; seq: number };
