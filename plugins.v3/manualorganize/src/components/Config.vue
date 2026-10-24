<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  initialConfig: { type: Object, default: () => ({}) },
})

const emit = defineEmits(['save', 'close'])
const form = ref({})

function normalize(value) {
  const config = value || {}
  return {
    enabled: Boolean(config.enabled),
    show_sidebar_nav: config.show_sidebar_nav !== false,
    history_limit: Math.max(10, Math.min(Number(config.history_limit || 80), 200)),
  }
}

function save() {
  emit('save', { ...form.value })
}

watch(
  () => props.initialConfig,
  value => {
    form.value = normalize(value)
  },
  { immediate: true, deep: true },
)
</script>

<template>
  <VForm class="manual-config" @submit.prevent="save">
    <VToolbar color="transparent" density="comfortable">
      <div class="text-h6">手动整理设置</div>
      <VSpacer />
      <VBtn icon="mdi-close" variant="text" aria-label="关闭" @click="emit('close')" />
    </VToolbar>
    <VDivider />

    <VAlert type="info" variant="tonal" class="ma-4">
      插件只在你点击预览或开始整理时工作，不会自动扫描目录。
    </VAlert>

    <div class="manual-config__body">
      <VSwitch
        v-model="form.enabled"
        color="primary"
        label="启用插件"
        hint="启用后才可使用手动整理工作台和接口。"
        persistent-hint
      />
      <VSwitch
        v-model="form.show_sidebar_nav"
        color="primary"
        label="显示侧栏入口"
        hint="在整理分组中显示“手动整理”。"
        persistent-hint
      />
      <VSlider
        v-model="form.history_limit"
        :min="10"
        :max="200"
        :step="10"
        label="近期下载数量"
        thumb-label="always"
        class="mt-6"
      />
      <div class="text-caption text-medium-emphasis">
        近期下载选择不读取远程目录，只查询下载历史；数量越大，下拉列表越长。
      </div>
    </div>

    <div class="manual-config__actions">
      <VBtn variant="text" @click="emit('close')">取消</VBtn>
      <VBtn color="primary" @click="save">保存</VBtn>
    </div>
  </VForm>
</template>

<style scoped>
.manual-config__body {
  display: grid;
  gap: 12px;
  padding: 0 18px 16px;
}

.manual-config__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 18px 14px;
}
</style>
