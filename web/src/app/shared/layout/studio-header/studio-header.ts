import { Component } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

@Component({
  selector: 'app-studio-header',
  imports: [RouterLink, RouterLinkActive],
  template: `
    <header class="header">
      <svg viewBox="0 0 24 24" aria-hidden="true">
        <path
          d="M6 2.5h11a2 2 0 0 1 2 2v13.2a.8.8 0 0 1-.8.8H7a1.5 1.5 0 0 0 0 3h11.2a.8.8 0 0 1 0 1.6H7a3.1 3.1 0 0 1-3.1-3.1V4.6A2.1 2.1 0 0 1 6 2.5Zm2.2 4a.8.8 0 0 0 0 1.6h7.6a.8.8 0 0 0 0-1.6H8.2Zm0 3.4a.8.8 0 0 0 0 1.6h5a.8.8 0 0 0 0-1.6h-5Z"
        />
      </svg>
      <h1>Book Publishing Studio</h1>
      <nav aria-label="Secciones">
        <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Estudio</a>
        <a routerLink="/importar" routerLinkActive="active">Importar PDF</a>
      </nav>
    </header>
  `,
  styles: `
    :host { display: block; position: relative; z-index: 2; }
    .header { display: flex; align-items: center; gap: .75rem; padding: 1rem 1.25rem; background: #fff; box-shadow: 0 1px 4px rgb(0 0 0 / 12%); }
    svg { width: 2rem; height: 2rem; fill: #6366f1; }
    h1 { margin: 0; font-size: 1.5rem; font-weight: 700; color: #1f2937; }
    nav { margin-left: auto; display: flex; gap: .25rem; }
    nav a { padding: .45rem .8rem; border-radius: .4rem; color: #4b5563; text-decoration: none; font-weight: 600; font-size: .9rem; }
    nav a:hover { background: #f3f4f6; }
    nav a.active { background: #eef2ff; color: #4338ca; }
  `,
})
export class StudioHeader {}
