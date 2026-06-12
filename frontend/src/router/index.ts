import { createRouter, createWebHistory } from "vue-router";
import ReportView from "@/views/ReportView.vue";
import CellsView from "@/views/CellsView.vue";
import ForwardView from "@/views/ForwardView.vue";
import DebugView from "@/views/DebugView.vue";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/report" },
    { path: "/report", name: "report", component: ReportView },
    { path: "/cells", name: "cells", component: CellsView },
    { path: "/forward", name: "forward", component: ForwardView },
    { path: "/debug", name: "debug", component: DebugView }
  ]
});
