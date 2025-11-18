import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'Cluster',
    component: () => import('./views/ClusterView.vue'),
    meta: { icon: '⬢', displayName: 'Cluster' }
  },
  {
    path: '/scenarios',
    name: 'Scenarios',
    component: () => import('./views/ScenariosView.vue'),
    meta: { icon: '⚡', displayName: 'Scenarios' }
  },
  {
    path: '/scenario-builder',
    name: 'ScenarioBuilder',
    component: () => import('./views/ScenarioBuilderView.vue'),
    meta: { icon: '⚙️', displayName: 'Builder' }
  },
  {
    path: '/datapools',
    name: 'Datapools',
    component: () => import('./views/DatapoolView.vue'),
    meta: { icon: '💾', displayName: 'Datapools' }
  },
  {
    path: '/metrics',
    name: 'Metrics',
    component: () => import('./views/MetricsView.vue'),
    meta: { icon: '◈', displayName: 'Metrics' }
  },
  {
    path: '/graphs',
    name: 'Graphs',
    component: () => import('./views/GraphsView.vue'),
    meta: { icon: '▲', displayName: 'Graphs' }
  },
  {
    path: '/historical',
    name: 'Historical',
    component: () => import('./views/HistoricalView.vue'),
    meta: { icon: '◉', displayName: 'Historical' }
  },
  {
    path: '/reports',
    name: 'Reports',
    component: () => import('./views/ReportsView.vue'),
    meta: { icon: '▣', displayName: 'Reports' }
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
