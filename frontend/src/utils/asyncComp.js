import { defineAsyncComponent, h } from 'vue'
import { t } from '../i18n'

function retryingAsync(loader, {
  retries = 3,
  delay = 120,
  retryDelay = 250,
  loadingComponent,
  errorComponent,
} = {}) {
  return defineAsyncComponent({
    loader,
    delay,
    loadingComponent,
    errorComponent,
    onError(error, retry, fail, attempts) {
      if (attempts <= retries) setTimeout(retry, retryDelay)
      else fail(error)
    },
  })
}

export function lazyView(loader, { label = '', retries = 2, delay = 80, retryDelay = 250, onRetry = null, retryLabel = '' } = {}) {
  const loadingComponent = {
    name: 'LazyViewLoading',
    render() {
      return h('div', {
        class: 'lazy-view-fallback',
        role: 'status',
        'aria-live': 'polite',
      }, [
        h('span', { class: 'scene-load-spinner', 'aria-hidden': 'true' }),
        h('span', label ? t('正在加载「{name}」…', { name: label }) : t('正在加载视图…')),
      ])
    },
  }

  const errorComponent = {
    name: 'LazyViewError',
    props: { error: Object },
    setup(props) {
      return () => h('div', { class: 'lazy-view-fallback error', role: 'alert' }, [
        h('strong', t('视图加载失败，请重试')),
        h('span', (props.error && props.error.message) || String(props.error || '')),
        // 自动重试耗尽后，Vue 不会再自己重试（切走再切回也一样）——给一个显式的重试按钮。
        // 宿主传 onRetry 时渲染重试按钮。注意：动态 import 的失败结果会被浏览器按模块 URL 缓存，
        // 单纯重挂载组件（改 :key）并不能重新发请求，宿主应给「重新加载页面」这类一定能恢复的动作。
        onRetry ? h('button', { class: 'lazy-retry-btn', type: 'button', onClick: () => onRetry() }, retryLabel || t('重试')) : null,
      ])
    },
  }

  return retryingAsync(loader, { retries, delay, retryDelay, loadingComponent, errorComponent })
}

// 对话框类异步组件统一封装：
// 解决「偶尔打不开」——裸 defineAsyncComponent 在动态 import 偶发失败（网络抖动、
// dev 热更新 chunk 失效、构建缓存不一致）时静默空白，无加载态、无重试、无任何提示。
// 本封装提供：
//  1. loadingComponent：加载期间显示「加载中…」占位（默认 Vue 加载期间是空白）
//  2. onError 自动重试：加载失败自动重试 retries 次（默认 2 次）
//  3. errorComponent：仍失败时显示可见错误提示，而不是空白无响应
export function lazyDialog(loader, { retries = 3, delay = 120, retryDelay = 250 } = {}) {
  const loadingComponent = {
    name: 'LazyLoading',
    render() {
      return h('div', {
        class: 'lazy-dialog-fallback',
        style: 'padding:32px;text-align:center;color:#9d9d9d;font-size:13px;font-family:var(--ui,system-ui);'
      }, t('加载中…'))
    },
  }

  const errorComponent = {
    name: 'LazyError',
    props: { error: Object },
    setup(props, { emit }) {
      return () => h('div', {
        class: 'lazy-dialog-fallback',
        style: 'padding:32px;text-align:center;color:#e06c75;font-size:13px;line-height:1.8;font-family:var(--ui,system-ui);'
      }, [
        h('div', { style: 'font-weight:600;margin-bottom:4px;' }, t('弹窗加载失败，请重试')),
        h('div', { style: 'font-size:11px;color:#8a8a8a;word-break:break-all;' }, (props.error && props.error.message) || String(props.error || '')),
      ])
    },
  }

  return defineAsyncComponent({
    loader,
    delay,
    loadingComponent,
    errorComponent,
    onError(error, retry, fail, attempts) {
      // 网络抖动/瞬时故障：延迟后自动重试；多次仍失败才放弃（重开弹窗会再次尝试加载）
      if (attempts <= retries) {
        setTimeout(retry, retryDelay)
      } else {
        fail(error)
      }
    },
  })
}
