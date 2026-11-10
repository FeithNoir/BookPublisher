import { Component, HostListener, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { StudioStore } from '../../core/studio.store';

const PAGE_SIZES: [string, string][] = [
  ['a4', 'A4 (210 × 297 mm)'],
  ['a5', 'A5 (148 × 210 mm)'],
  ['b5', 'B5 (176 × 250 mm)'],
  ['6x9', '6 × 9 in (trade)'],
  ['5.5x8.5', '5,5 × 8,5 in'],
  ['carta', 'Carta (8,5 × 11 in)'],
];

@Component({
  selector: 'app-studio',
  imports: [DecimalPipe],
  templateUrl: './studio.html',
  styleUrl: './studio.css',
})
export class Studio {
  protected readonly store = inject(StudioStore);
  protected readonly pageSizes = PAGE_SIZES;
  protected readonly pasteOpen = signal(false);
  protected readonly pasteText = signal('');
  protected readonly dragging = signal(false);
  protected readonly showDetail = signal(false);

  protected readonly selectedIndex = computed(() => {
    const t = this.store.target();
    return t === 'cover' ? -1 : Number(t);
  });

  protected readonly currentLabel = computed(() => {
    const d = this.store.doc();
    const i = this.selectedIndex();
    if (!d) return '';
    if (i < 0) return 'Portada e índice';
    const c = d.chapters[i];
    return [c.label, c.title].filter(Boolean).join(' · ') || `Capítulo ${i + 1}`;
  });

  protected onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const f = input.files?.[0];
    if (f) this.store.open(f);
    input.value = '';
  }

  protected onDrop(ev: DragEvent): void {
    ev.preventDefault();
    this.dragging.set(false);
    const f = ev.dataTransfer?.files?.[0];
    if (f) this.store.open(f);
  }

  protected openPasted(): void {
    const text = this.pasteText().trim();
    if (!text) return;
    this.store.openText(text, 'texto-pegado');
    this.pasteOpen.set(false);
  }

  protected num(v: string): number | null {
    const n = parseFloat(v.replace(',', '.'));
    return Number.isFinite(n) ? n : null;
  }

  protected fmtTime(s: number | null | undefined): string {
    if (s == null || !Number.isFinite(s)) return '—';
    if (s < 1) return `${Math.max(0.1, s).toFixed(1)} s`;
    if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)} s`;
    const m = Math.floor(s / 60);
    return `${m} min ${Math.round(s % 60)} s`;
  }

  protected fmtSize(b: number | undefined): string {
    if (!b) return '—';
    return b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : `${Math.round(b / 1e3)} kB`;
  }

  protected phaseLabel(p: string): string {
    return (
      { cola: 'En cola', maquetar: 'Maquetando', foliar: 'Numerando páginas', portada: 'Portada e índice', unir: 'Uniendo', docx: 'Escribiendo Word' } as Record<string, string>
    )[p] ?? p;
  }

  @HostListener('document:keydown', ['$event'])
  protected onKey(e: KeyboardEvent): void {
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
    if (e.key === 'ArrowRight' || e.key === 'PageDown') this.store.step(1);
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') this.store.step(-1);
    if (e.key === 'Escape' && this.store.busy()) this.store.cancelExport();
  }
}
