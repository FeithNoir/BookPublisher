import { Injectable } from '@angular/core';
import { DocumentOutline, ExportOptions, JobEvent, JobSummary, PreviewResult, Theme } from './models';

/** Error de la API con el mensaje legible que manda el servidor. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail = '',
  ) {
    super(message);
  }
}

@Injectable({ providedIn: 'root' })
export class ApiService {
  private async call<T>(url: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await fetch(url, init);
    } catch {
      throw new ApiError('No hay conexión con el motor local. ¿Está corriendo «bookpublisher serve»?', 0);
    }
    const body = await res.json().catch(() => null);
    if (!res.ok) {
      const msg = body?.detail ?? body?.error ?? `Error ${res.status}`;
      throw new ApiError(typeof msg === 'string' ? msg : JSON.stringify(msg), res.status, body?.detail ?? '');
    }
    return body as T;
  }

  themes(): Promise<Theme[]> {
    return this.call('/api/themes');
  }

  openFile(file: File): Promise<DocumentOutline> {
    const fd = new FormData();
    fd.append('file', file);
    return this.call('/api/documents', { method: 'POST', body: fd });
  }

  openText(text: string, name: string): Promise<DocumentOutline> {
    const fd = new FormData();
    fd.append('text', text);
    fd.append('name', name);
    return this.call('/api/documents', { method: 'POST', body: fd });
  }

  outline(id: string): Promise<DocumentOutline> {
    return this.call(`/api/documents/${id}`);
  }

  preview(id: string, target: string, options: ExportOptions, signal?: AbortSignal): Promise<PreviewResult> {
    return this.call(`/api/documents/${id}/preview?target=${encodeURIComponent(target)}&pages=4`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(options),
      signal,
    });
  }

  startExport(document: string, format: 'pdf' | 'docx' | 'md', options: ExportOptions): Promise<JobSummary> {
    return this.call('/api/exports', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document, format, options }),
    });
  }

  startImport(file: File, images: boolean, tables: boolean): Promise<JobSummary> {
    const fd = new FormData();
    fd.append('file', file);
    fd.append('images', String(images));
    fd.append('tables', String(tables));
    return this.call('/api/imports', { method: 'POST', body: fd });
  }

  cancel(jobId: string): Promise<unknown> {
    return this.call(`/api/jobs/${jobId}/cancel`, { method: 'POST' });
  }

  fileUrl(jobId: string, kind: string, inline = false): string {
    return `/api/jobs/${jobId}/files/${kind}${inline ? '?inline=true' : ''}`;
  }

  /** Sigue los eventos de un trabajo (SSE). Devuelve la función para dejar de escuchar. */
  follow(jobId: string, onEvent: (e: JobEvent) => void, onEnd: () => void): () => void {
    const es = new EventSource(`/api/jobs/${jobId}/events`);
    es.onmessage = (m) => onEvent(JSON.parse(m.data) as JobEvent);
    es.addEventListener('end', () => {
      es.close();
      onEnd();
    });
    return () => es.close();
  }
}
