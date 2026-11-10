import { Component, OnDestroy, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { StudioStore } from '../../core/studio.store';

interface ImportState {
  jobId: string;
  file: string;
  status: 'running' | 'done' | 'error' | 'cancelled';
  message: string;
  page: number;
  pages: number;
  startedAt: number;
  elapsed: number;
  result: Record<string, any> | null;
  error: string | null;
}

@Component({
  selector: 'app-import-page',
  templateUrl: './import-page.html',
  styleUrl: './import-page.css',
})
export class ImportPage implements OnDestroy {
  private readonly api = inject(ApiService);
  private readonly store = inject(StudioStore);
  private readonly router = inject(Router);
  protected readonly images = signal(true);
  protected readonly tables = signal(true);
  protected readonly dragging = signal(false);
  protected readonly state = signal<ImportState | null>(null);
  private stop: (() => void) | null = null;
  private timer: ReturnType<typeof setInterval> | null = null;

  protected onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    if (f) this.start(f);
    input.value = '';
  }

  protected onDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(false);
    const f = ev.dataTransfer?.files?.[0];
    if (f) this.start(f);
  }

  protected async start(file: File): Promise<void> {
    if (this.state()?.status === 'running') return;
    this.stop?.();
    const startedAt = performance.now();
    this.state.set({ jobId: '', file: file.name, status: 'running', message: 'Subiendo…', page: 0, pages: 0, startedAt, elapsed: 0, result: null, error: null });
    this.timer = setInterval(() => this.upd({ elapsed: (performance.now() - startedAt) / 1000 }), 200);
    try {
      const job = await this.api.startImport(file, this.images(), this.tables());
      this.upd({ jobId: job.id, message: 'En cola…' });
      this.stop = this.api.follow(
        job.id,
        (ev) => {
          if (ev.type === 'phase') this.upd({ message: ev.message });
          if (ev.type === 'page') this.upd({ page: ev.done, pages: ev.total });
          if (ev.type === 'finished') this.finish({ status: 'done', result: ev.result, message: 'Listo' });
          if (ev.type === 'error') this.finish({ status: 'error', error: ev.message });
          if (ev.type === 'cancelled') this.finish({ status: 'cancelled', message: 'Importación cancelada' });
        },
        () => this.clearTimer(),
      );
    } catch (e) {
      this.finish({ status: 'error', error: (e as Error).message });
    }
  }

  protected cancel(): void {
    const s = this.state();
    if (s?.jobId) this.api.cancel(s.jobId);
  }

  protected url(kind: string): string {
    return this.api.fileUrl(this.state()?.jobId ?? '', kind);
  }

  protected async openInStudio(): Promise<void> {
    const id = this.state()?.result?.['document'];
    if (!id) return;
    await this.store.openExisting(id);
    this.router.navigateByUrl('/');
  }

  protected percent(s: ImportState): number {
    if (s.status === 'done') return 100;
    if (!s.pages) return 2;
    return Math.min(95, (s.page / s.pages) * 90);
  }

  ngOnDestroy(): void {
    this.stop?.();
    this.clearTimer();
  }

  private finish(p: Partial<ImportState>): void {
    this.clearTimer();
    this.upd({ ...p, elapsed: (performance.now() - (this.state()?.startedAt ?? 0)) / 1000 });
  }

  private upd(p: Partial<ImportState>): void {
    this.state.update((s) => (s ? { ...s, ...p } : s));
  }

  private clearTimer(): void {
    if (this.timer) clearInterval(this.timer);
    this.timer = null;
  }
}
