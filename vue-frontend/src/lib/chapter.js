// v5.6.0 P2 · 章回主题「全站语言层」的共享判定
//
// 为什么是函数而不是模块级 computed：
// - `state.site.theme_bundle` 由 initSite() 在首屏之后才写入，模块级常量会
//   拿不到后到的数据；函数调用发生在 render 期间，天然被 Vue 依赖收集。
// - 各视图模板里写 `v-if="chapterOn()"`，不需要关心 ref 自动解包规则。
// - 主题包损坏 / 未激活时恒返回 false，经典主题 DOM 一行不变（零影响契约）。
//
// 注意：这里只读**展示层**（public_bundle），不引入 theme_bundles.py 的
// schema 字段，也不新增任何接口 —— 主题包契约保持 v5.5.0 原样。
import { state } from "../store.js";

export function chapterOn() {
  const b = state.site && state.site.theme_bundle;
  return !!(b && b.layout && b.layout.mode === "chapter");
}

export function chapterLabels() {
  const b = state.site && state.site.theme_bundle;
  return (b && b.labels) || {};
}
