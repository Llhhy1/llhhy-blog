// 路由表
import { createRouter, createWebHistory } from "vue-router";

const routes = [
  { path: "/", name: "home", component: () => import("./views/HomeView.vue") },
  { path: "/post/:slug", name: "post", component: () => import("./views/PostView.vue") },
  { path: "/category/:slug", name: "category", component: () => import("./views/CategoryView.vue") },
  { path: "/tag/:slug", name: "tag", component: () => import("./views/TagView.vue") },
  { path: "/archive", name: "archive", component: () => import("./views/ArchiveView.vue") },
  { path: "/stats", name: "stats", component: () => import("./views/StatsView.vue") },
  { path: "/about", name: "about", component: () => import("./views/AboutView.vue") },
  { path: "/links", name: "links", component: () => import("./views/LinksView.vue") },
  { path: "/square", name: "square", component: () => import("./views/SquareView.vue") },
  { path: "/series", name: "series", component: () => import("./views/SeriesView.vue") },
  { path: "/series/:slug", name: "series-detail", component: () => import("./views/SeriesDetailView.vue") },
  { path: "/tags/hot", name: "hot-tags", component: () => import("./views/HotTagsView.vue") },
  { path: "/guestbook", name: "guestbook", component: () => import("./views/GuestbookView.vue") },
  { path: "/unsubscribe", name: "unsubscribe", component: () => import("./views/UnsubscribeView.vue") },
  { path: "/search", name: "search", component: () => import("./views/SearchView.vue") },
  { path: "/login", name: "login", component: () => import("./views/LoginView.vue") },
  { path: "/register", name: "register", component: () => import("./views/RegisterView.vue") },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export default createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior() { return { top: 0 }; },
});
