<template>
  <div class="ab-mask" @click.self="$emit('close')">
    <div class="ab-modal" role="dialog" aria-modal="true" aria-label="关于本平台">
      <div class="ab-logo">
        <img src="/favicon.png" alt="工业能碳智控平台" />
      </div>

      <div class="ab-name">工业能碳智控平台</div>
      <div class="ab-sub">Web 版工业数字孪生仿真系统</div>
      <div class="ab-sub">面向高炉炼铁的能碳仿真与优化平台</div>
      <div class="ab-ver">版本 v0.1.0</div>

      <div class="ab-divider"></div>
      <div class="ab-copy">© 2026 haiyisoftware · 保留所有权利</div>

      <div class="ab-foot">
        <button class="ab-ok" @click="$emit('close')">确 定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineEmits(['close'])
</script>

<style scoped>
.ab-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ab-modal { width: 420px; max-width: 92vw; background: var(--panel); border: 1px solid var(--border);
  border-radius: 10px; box-shadow: 0 18px 50px rgba(0,0,0,.3); font-family: var(--ui); color: var(--text);
  padding: 30px 36px 22px; display: flex; flex-direction: column; align-items: center; text-align: center; }

.ab-logo { width: 84px; height: 84px; border-radius: 16px; overflow: hidden; border: 1px solid var(--border);
  box-shadow: 0 6px 18px rgba(0,0,0,.18); display: flex; align-items: center; justify-content: center;
  background: var(--panel-2); }
.ab-logo img { width: 100%; height: 100%; object-fit: cover; }

.ab-name { margin-top: 18px; font-size: 19px; font-weight: 700; letter-spacing: 1.5px; }
.ab-sub { margin-top: 5px; font-size: 12px; line-height: 1.6; color: var(--muted); }
.ab-ver { margin-top: 14px; font-size: 12px; color: var(--accent); font-family: var(--mono); }

.ab-divider { margin-top: 18px; width: 100%; border-top: 1px solid var(--border); }
.ab-copy { margin-top: 14px; font-size: 12px; color: var(--faint); font-family: var(--mono); letter-spacing: .3px; }

.ab-foot { margin-top: 20px; width: 100%; display: flex; justify-content: flex-end; }
.ab-ok { min-width: 96px; padding: 7px 0; font-size: 13px; font-family: var(--ui); border-radius: 4px; cursor: pointer;
  color: var(--accent); background: transparent; border: 1px solid var(--accent); }
.ab-ok:hover { color: #fff; background: var(--accent); border-color: var(--accent); }
</style>
