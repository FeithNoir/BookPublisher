import { Injectable, computed, effect, inject, signal, untracked } from '@angular/core';
import { ApiError, ApiService } from './api.service';
import { DocumentOutline, ExportOptions, JobEvent, PreviewResult, Theme } from './models';

export type ChapterState = 'pendiente' | 'maquetando' | 'listo' | 'cache';
export type Format = 'pdf' | 'docx' | 'md';

export interface ExportState {
  jobId: string;
  format: Format;
  status: 'running' | 'done' | 'error' | 'cancelled';
  phase: string;
  message: string;
  percent: number;
  done: number;
  total: number;
  etaSeconds: number | null;
  elapsed: number;
  startedAt: number;
  result: Record<string, any> | null;
  error: { message: string; chapter: string | null; detail: string } | null;
}

const PHASES: Record<string, [number, number]> = {
  maquetar: [0, 0.6],
  foliar: [0.6, 0.92],
  portada: [0.92, 0.95],
  unir: [0.95, 0.99],
};

const LS_KEY = 'bookpublisher.options.v1';

@Injectable({ providedIn: 'root' })
export class StudioStore {
  private readonly api = inject(ApiService);

  readonly themes = signal<Theme[]>([]);
  readonly doc = signal<DocumentOutline | null>(null);
  readonly opening = signal(false);
  readonly openError = signal<string | null>(null);
  readonly options = signal<ExportOptions>(this.loadOptions());
  readonly target = signal<string>('cover');
  readonly preview = signal<PreviewResult | null>(null);
  readonly previewLoading = signal(false);
  readonly previewError = signal<{ message: string; detail: string } | null>(null);
  readonly exportState = signal<ExportState | null>(null);
  readonly chapterStates = signal<Record<number, ChapterState>>({});

  readonly theme = computed(() => this.themes().find((t) => t.id === this.options().theme) ?? null);
  /** Opciones con los valores por defecto del tema rellenados (para mostrarlas en los controles). */
  readonly effective = computed(() => {
    const o = this.options();
    const d = this.theme()?.defaults;
    return {
      page_size: o.page_size ?? d?.page_size ?? 'a5',
      font_size: o.font_size ?? d?.font_size ?? 11,
      chapter_break: o.chapter_break ?? d?.chapter_break ?? 'page',
      dropcaps: o.dropcaps ?? d?.dropcaps ?? false,
    };
  });
  readonly estimate = computed(() => this.doc()?.estimates?.[this.options().theme] ?? null);
  readonly busy = computed(() => this.exportState()?.status === 'running');

  private stopFollow: (() => void) | null = null;
  private previewAbort: AbortController | null = null;
  private previewTimer: ReturnType<typeof setTimeout> | null = null;
  private tick: ReturnType<typeof setInterval> | null = null;

  constructor() {
    this.api
      .themes()
      .then((t) => this.themes.set(t))
      .catch((e: ApiError) => this.openError.set(e.message));

    // Vista previa: se recalcula (con un pequeño retardo) al cambiar documento, opciones o capítulo.
    effect(() => {
      const doc = this.doc();
      const opts = this.options();
      const target = this.target();
      if (!doc) return;
      untracked(() => this.schedulePreview(doc.id, target, opts));
    });
    effect(() => {
      localStorage.setItem(LS_KEY, JSON.stringify(this.options()));
    });
  }

  // ------------------------------------------------------------ documento
  async open(file: File): Promise<void> {
    await this.load(() => this.api.openFile(file));
  }

  async openText(text: string, name: string): Promise<void> {
    await this.load(() => this.api.openText(text, name));
  }

  async openExisting(id: string): Promise<void> {
    await this.load(() => this.api.outline(id));
  }

  private async load(fn: () => Promise<DocumentOutline>): Promise<void> {
    this.opening.set(true);
    this.openError.set(null);
    try {
      const d = await fn();
      this.doc.set(d);
      this.chapterStates.set({});
      this.exportState.set(null);
      this.target.set('cover');
      this.patch({ title: null, author: null });
    } catch (e) {
      this.openError.set((e as Error).message);
    } finally {
      this.opening.set(false);
    }
  }

  close(): void {
    this.doc.set(null);
    this.preview.set(null);
    this.exportState.set(null);
  }

  // ------------------------------------------------------------- opciones
  patch(p: Partial<ExportOptions>): void {
    this.options.update((o) => ({ ...o, ...p }));
  }

  setTheme(id: string): void {
    // Al cambiar de tema vuelven sus valores por defecto (tamaño, cuerpo, saltos).
    this.patch({ theme: id, page_size: null, font_size: null, chapter_break: null, dropcaps: null });
  }

  selectChapter(target: string): void {
    this.target.set(target);
  }

  step(delta: number): void {
    const d = this.doc();
    if (!d) return;
    const cur = this.target() === 'cover' ? -1 : Number(this.target());
    const next = Math.max(-1, Math.min(d.chapters.length - 1, cur + delta));
    this.target.set(next < 0 ? 'cover' : String(next));
  }

  private schedulePreview(id: string, target: string, opts: ExportOptions): void {
    if (this.previewTimer) clearTimeout(this.previewTimer);
    this.previewTimer = setTimeout(() => this.runPreview(id, target, opts), 220);
  }

  private async runPreview(id: string, target: string, opts: ExportOptions): Promise<void> {
    this.previewAbort?.abort();
    const ctrl = new AbortController();
    this.previewAbort = ctrl;
    this.previewLoading.set(true);
    this.previewError.set(null);
    try {
      const r = await this.api.preview(id, target, opts, ctrl.signal);
      if (!ctrl.signal.aborted) this.preview.set(r);
    } catch (e) {
      if (ctrl.signal.aborted) return;
      const err = e as ApiError;
      this.previewError.set({ message: err.message, detail: err.detail ?? '' });
    } finally {
      if (this.previewAbort === ctrl) this.previewLoading.set(false);
    }
  }

  // ------------------------------------------------------------- exportar
  async export(format: Format): Promise<void> {
    const d = this.doc();
    if (!d || this.busy()) return;
    this.stopFollow?.();
    const states: Record<number, ChapterState> = {};
    d.chapters.forEach((c) => (states[c.index] = 'pendiente'));
    this.chapterStates.set(format === 'pdf' ? states : {});
    const startedAt = performance.now();
    this.exportState.set({
      jobId: '',
      format,
      status: 'running',
      phase: 'cola',
      message: 'Preparando…',
      percent: 0,
      done: 0,
      total: d.chapters.length,
      etaSeconds: format === 'pdf' ? this.estimate() : null,
      elapsed: 0,
      startedAt,
      result: null,
      error: null,
    });
    this.startTick();
    try {
      const job = await this.api.startExport(d.id, format, this.options());
      this.exportState.update((s) => (s ? { ...s, jobId: job.id } : s));
      let chunkMap: 'uno' | 'todos' = 'uno';
      this.stopFollow = this.api.follow(
        job.id,
        (ev) => {
          if (ev.type === 'plan') chunkMap = ev.chunks === ev.chapters ? 'uno' : 'todos';
          this.onEvent(ev, chunkMap);
        },
        () => this.stopTick(),
      );
    } catch (e) {
      this.fail({ message: (e as Error).message, chapter: null, detail: '' });
    }
  }

  async cancelExport(): Promise<void> {
    const s = this.exportState();
    if (!s?.jobId || s.status !== 'running') return;
    this.exportState.update((x) => (x ? { ...x, message: 'Cancelando…' } : x));
    await this.api.cancel(s.jobId).catch(() => undefined);
  }

  dismissExport(): void {
    this.exportState.set(null);
    this.chapterStates.set({});
  }

  fileUrl(kind: string, inline = false): string | null {
    const s = this.exportState();
    return s?.jobId ? this.api.fileUrl(s.jobId, kind, inline) : null;
  }

  private onEvent(ev: JobEvent, chunkMap: 'uno' | 'todos'): void {
    const upd = (p: Partial<ExportState>) => this.exportState.update((s) => (s ? { ...s, ...p } : s));
    switch (ev.type) {
      case 'phase': {
        const base = PHASES[ev.phase]?.[0];
        upd({ phase: ev.phase, message: ev.message, ...(base !== undefined ? { percent: Math.max(this.exportState()?.percent ?? 0, base) } : {}) });
        if (ev.phase === 'maquetar' || ev.phase === 'foliar') upd({ done: 0, total: ev.total ?? 0 });
        break;
      }
      case 'chunk': {
        const [a, b] = PHASES[ev.phase] ?? [0, 1];
        const frac = ev.words_total ? ev.words_done / ev.words_total : ev.done / ev.total;
        const percent = a + (b - a) * frac;
        const elapsed = (performance.now() - (this.exportState()?.startedAt ?? 0)) / 1000;
        const eta = percent > 0.04 ? (elapsed * (1 - percent)) / percent : this.exportState()?.etaSeconds ?? null;
        upd({ percent, done: ev.done, total: ev.total, etaSeconds: eta });
        const st: ChapterState = ev.cached ? 'cache' : 'listo';
        this.chapterStates.update((m) => {
          const n = { ...m };
          if (chunkMap === 'uno') {
            if (ev.phase === 'maquetar' || n[ev.index] === 'pendiente') n[ev.index] = st;
          } else {
            Object.keys(n).forEach((k) => (n[+k] = st));
          }
          return n;
        });
        break;
      }
      case 'finished':
        upd({ status: 'done', percent: 1, etaSeconds: 0, message: 'Listo', result: ev.result });
        this.stopTick();
        break;
      case 'error':
        this.fail({ message: ev.message, chapter: ev.chapter, detail: ev.detail });
        break;
      case 'cancelled':
        upd({ status: 'cancelled', message: 'Exportación cancelada', etaSeconds: null });
        this.chapterStates.set({});
        this.stopTick();
        break;
    }
  }

  private fail(error: ExportState['error']): void {
    this.exportState.update((s) => (s ? { ...s, status: 'error', error, etaSeconds: null } : s));
    this.stopTick();
  }

  private startTick(): void {
    this.stopTick();
    this.tick = setInterval(() => {
      this.exportState.update((s) =>
        s && s.status === 'running' ? { ...s, elapsed: (performance.now() - s.startedAt) / 1000 } : s,
      );
    }, 200);
  }

  private stopTick(): void {
    if (this.tick) clearInterval(this.tick);
    this.tick = null;
    this.exportState.update((s) => (s ? { ...s, elapsed: (performance.now() - s.startedAt) / 1000 } : s));
  }

  private loadOptions(): ExportOptions {
    const base: ExportOptions = {
      theme: 'novela',
      page_size: null,
      font_size: null,
      chapter_break: null,
      dropcaps: null,
      hyphenate: true,
      toc: true,
      cover: true,
      title: null,
      author: null,
    };
    try {
      const saved = JSON.parse(localStorage.getItem(LS_KEY) ?? 'null');
      return saved ? { ...base, ...saved, title: null, author: null } : base;
    } catch {
      return base;
    }
  }
}
