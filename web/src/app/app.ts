import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { StudioFooter } from './shared/layout/studio-footer/studio-footer';
import { StudioHeader } from './shared/layout/studio-header/studio-header';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, StudioHeader, StudioFooter],
  template: `
    <div class="shell">
      <app-studio-header />
      <main><router-outlet /></main>
      <app-studio-footer />
    </div>
  `,
  styles: `
    .shell { display: grid; grid-template-rows: auto 1fr auto; height: 100vh; }
    main { min-height: 0; }
  `,
})
export class App {}
