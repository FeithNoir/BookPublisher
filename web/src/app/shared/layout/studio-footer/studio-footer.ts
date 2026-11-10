import { Component } from '@angular/core';

@Component({
  selector: 'app-studio-footer',
  template: `<footer>Desarrollado por <a href="https://github.com/FeithNoir" target="_blank" rel="noopener">feithnoir</a></footer>`,
  styles: `
    footer { padding: .9rem; text-align: center; font-size: .8rem; color: #4b5563; background: #fff; border-top: 1px solid #f3f4f6; }
    a { color: #4f46e5; font-weight: 600; }
  `,
})
export class StudioFooter {}
