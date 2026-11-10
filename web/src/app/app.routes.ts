import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', loadComponent: () => import('./features/studio/studio').then((m) => m.Studio), title: 'BookPublisher · Estudio' },
  {
    path: 'importar',
    loadComponent: () => import('./features/import/import-page').then((m) => m.ImportPage),
    title: 'BookPublisher · Importar PDF',
  },
  { path: '**', redirectTo: '' },
];
