import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Cluster',
    component: () => import('./views/ClusterView.vue'),
  },
  {
    path: '/scenarios',
    name: 'Scenarios',
    component: () => import('./views/ScenariosView.vue'),
  },
  {
    path: '/metrics',
    name: 'Metrics',
    component: () => import('./views/MetricsView.vue'),
  },
  {
    path: '/graphs',
    name: 'Graphs',
    component: () => import('./views/GraphsView.vue'),
  },
  {
    path: '/historical',
    name: 'Historical',
    component: () => import('./views/HistoricalView.vue'),
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('./views/ReportsView.vue'),
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
