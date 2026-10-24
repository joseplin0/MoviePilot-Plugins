<script setup>
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  api: { type: Object, default: () => ({}) },
  pluginId: { type: String, default: 'ManualOrganize' },
})

const mode = ref('history')
const options = ref({ sources: [], storages: [], directory_roots: [], history_limit: 80 })
const selectedHistoryId = ref(null)
const manual = ref({ storage: 'local', path: '', item_type: 'dir' })
const loading = ref(false)
const loadingOptions = ref(false)
const confirmOpen = ref(false)
const result = ref(null)
const error = ref('')
const notice = ref('')

const pluginBase = computed(() => `plugin/${props.pluginId || 'ManualOrganize'}`)
const selectedSource = computed(() =>
  options.value.sources.find(item => item.history_id === selectedHistoryId.value),
)
const selectedStorage = computed(() =>
  options.value.storages.find(item => item.value === manual.value.storage),
)
const canSubmit = computed(() => {
  if (loading.value) return false
  if (mode.value === 'history') return Boolean(selectedHistoryId.value)
  return Boolean(String(manual.value.path || '').trim())
})

function requestPayload() {
  if (mode.value === 'history') {
    return { mode: 'history', history_id: selectedHistoryId.value }
  }
  return {
    mode: 'path',
    storage: manual.value.storage,
    path: String(manual.value.path || '').trim(),
    item_type: manual.value.item_type,
  }
}

async function loadOptions() {
  loadingOptions.value = true
  error.value = ''
  try {
    const response = await props.api.get(`${pluginBase.value}/options`, {
      feedback: 'silent',
    })
    if (!response?.success) {
      error.value = response?.message || '读取近期下载失败'
      return
    }
    options.value = response.data || options.value
    if (!selectedHistoryId.value && options.value.sources.length) {
      selectedHistoryId.value = options.value.sources[0].history_id
    }
  } catch {
    error.value = '读取近期下载失败，请确认插件已启用。'
  } finally {
    loadingOptions.value = false
  }
}

async function invoke(action) {
  if (!canSubmit.value) return
  loading.value = true
  error.value = ''
  notice.value = ''
  result.value = null
  try {
    const response = await props.api.post(
      `${pluginBase.value}/${action}`,
      requestPayload(),
      { feedback: 'silent' },
    )
    result.value = response?.data || null
    if (!response?.success) {
      error.value = response?.message || '手动整理未完成'
      return
    }
    notice.value = action === 'preview' ? '预览完成，确认目标无误后可开始整理。' : completedNotice(response.data)
    if (action === 'organize') await loadOptions()
  } catch {
    error.value = '请求执行失败，请查看插件日志和 MoviePilot 整理日志。'
  } finally {
    loading.value = false
  }
}

function completedNotice(data) {
  if (!data) return '整理请求已完成。'
  if (data.completed > 0 && data.completed === data.total) {
    return `整理完成，共 ${data.completed} 个文件确认入库。`
  }
  if (data.accepted > 0) return '任务已接收，但尚未确认入库，请到整理队列查看。'
  if (data.retry_wait > 0) return '任务正在等待自动重试，请稍后检查整理记录。'
  if (data.manual_review > 0) return '任务需要人工复核，请到整理任务中处理。'
  return data.message || '整理执行结束，请查看逐文件状态。'
}

function sourceSubtitle(item) {
  const parts = [item.path]
  if (item.date) parts.push(item.date)
  if (item.organized) parts.push('已有成功整理记录')
  return parts.join(' · ')
}

function statusText(item) {
  const labels = {
    completed: '已入库',
    accepted: '已接收',
    failed: '失败',
    retry_wait: '待重试',
    skipped: '已跳过',
    manual_review: '待复核',
  }
  return labels[item.state] || (item.success ? '成功' : '未完成')
}

function statusColor(item) {
  const colors = {
    completed: 'success',
    accepted: 'info',
    failed: 'error',
    retry_wait: 'warning',
    skipped: 'default',
    manual_review: 'warning',
  }
  return colors[item.state] || (item.success ? 'success' : 'error')
}

function openConfirm() {
  if (!canSubmit.value) return
  confirmOpen.value = true
}

onMounted(loadOptions)
</script>

<template>
  <div class="manual-page">
    <VCard variant="flat" class="manual-page__card">
      <VCardTitle class="d-flex align-center flex-wrap ga-2">
        <VIcon icon="mdi-folder-sync-outline" color="primary" />
        <span>手动整理</span>
        <VSpacer />
        <VBtn
          icon="mdi-refresh"
          variant="text"
          :loading="loadingOptions"
          aria-label="刷新近期下载"
          @click="loadOptions"
        />
      </VCardTitle>
      <VCardSubtitle>
        处理订阅下载后没有触发入库，或远程挂载目录无法在文件管理中展开的情况。
      </VCardSubtitle>
      <VCardText>
        <VAlert type="info" variant="tonal" class="mb-4">
          “近期下载”直接使用下载历史里的文件清单，不列远程目录；“手工地址”可输入准确文件或目录。输入单个文件最稳，输入目录仍会由 MoviePilot 扫描目录内容。
        </VAlert>

        <VBtnToggle v-model="mode" mandatory color="primary" variant="outlined" class="mb-4">
          <VBtn value="history" prepend-icon="mdi-history">选择近期下载</VBtn>
          <VBtn value="path" prepend-icon="mdi-form-textbox">输入地址</VBtn>
        </VBtnToggle>

        <div v-if="mode === 'history'" class="manual-page__section">
          <VAutocomplete
            v-model="selectedHistoryId"
            :items="options.sources"
            item-title="title"
            item-value="history_id"
            label="近期下载目录"
            placeholder="选择未触发入库的下载"
            :loading="loadingOptions"
            clearable
            no-data-text="没有可选的近期下载记录"
            hint="选项来自下载历史，不会打开或遍历远程挂载目录。"
            persistent-hint
          >
            <template #item="{ props: itemProps, item }">
              <VListItem v-bind="itemProps" :subtitle="sourceSubtitle(item.raw)">
                <template #append>
                  <VChip v-if="item.raw.organized" size="x-small" color="warning" variant="tonal">
                    已整理过
                  </VChip>
                </template>
              </VListItem>
            </template>
          </VAutocomplete>

          <VCard v-if="selectedSource" variant="tonal" class="mt-3">
            <VCardText class="manual-page__source-summary">
              <div><span>存储：</span>{{ selectedSource.storage }}</div>
              <div><span>类型：</span>{{ selectedSource.item_type === 'file' ? '单文件' : '目录' }}</div>
              <div class="manual-page__path"><span>地址：</span>{{ selectedSource.path }}</div>
            </VCardText>
          </VCard>
        </div>

        <div v-else class="manual-page__section">
          <VRow>
            <VCol cols="12" md="4">
              <VSelect
                v-model="manual.storage"
                :items="options.storages"
                item-title="title"
                item-value="value"
                label="源存储"
                :hint="selectedStorage?.hint || ''"
                persistent-hint
              />
            </VCol>
            <VCol cols="12" md="8">
              <VTextField
                v-model="manual.path"
                label="文件或目录地址"
                placeholder="/downloads/剧名"
                hint="也可直接输入带存储前缀的地址；前缀会覆盖左侧选择。"
                persistent-hint
                clearable
              />
            </VCol>
          </VRow>
          <div class="d-flex align-center flex-wrap ga-3 mt-2">
            <span class="text-body-2">地址类型</span>
            <VBtnToggle v-model="manual.item_type" mandatory density="comfortable" variant="outlined">
              <VBtn value="file" prepend-icon="mdi-file-video-outline">单个媒体文件</VBtn>
              <VBtn value="dir" prepend-icon="mdi-folder-outline">媒体目录</VBtn>
            </VBtnToggle>
          </div>
          <VAlert v-if="manual.item_type === 'dir'" type="warning" variant="tonal" density="compact" class="mt-3">
            目录整理需要 MoviePilot 扫描内容；远程挂载较慢时优先输入准确媒体文件，或改用“近期下载”。
          </VAlert>
        </div>

        <VExpansionPanels v-if="options.directory_roots.length" variant="accordion" class="mt-5">
          <VExpansionPanel>
            <VExpansionPanelTitle>当前可匹配的整理目录规则（{{ options.directory_roots.length }}）</VExpansionPanelTitle>
            <VExpansionPanelText>
              <VList lines="two" density="compact">
                <VListItem
                  v-for="root in options.directory_roots"
                  :key="`${root.storage}:${root.path}:${root.target_path}`"
                  :title="root.name"
                  :subtitle="`${root.storage}:${root.path} → ${root.target_storage}:${root.target_path}`"
                />
              </VList>
            </VExpansionPanelText>
          </VExpansionPanel>
        </VExpansionPanels>

        <VAlert v-if="error" type="error" variant="tonal" class="mt-4" closable @click:close="error = ''">
          {{ error }}
        </VAlert>
        <VAlert v-if="notice" type="success" variant="tonal" class="mt-4" closable @click:close="notice = ''">
          {{ notice }}
        </VAlert>
      </VCardText>
      <VCardActions class="manual-page__actions">
        <VBtn
          variant="tonal"
          prepend-icon="mdi-eye-outline"
          :disabled="!canSubmit"
          :loading="loading"
          @click="invoke('preview')"
        >
          预览
        </VBtn>
        <VBtn
          color="primary"
          prepend-icon="mdi-play"
          :disabled="!canSubmit"
          :loading="loading"
          @click="openConfirm"
        >
          开始整理
        </VBtn>
      </VCardActions>
    </VCard>

    <VCard v-if="result" variant="outlined" class="manual-page__result mt-4">
      <VCardTitle>{{ result.preview ? '整理预览' : '整理结果' }}</VCardTitle>
      <VCardText>
        <div class="manual-page__result-paths">
          <div><span>来源：</span>{{ result.source_storage }}:{{ result.source_path }}</div>
          <div><span>目标：</span>{{ result.target_storage }}:{{ result.target_path }}</div>
          <div><span>发现方式：</span>{{ result.selection_strategy }}</div>
        </div>
        <div class="d-flex flex-wrap ga-2 my-4">
          <VChip>总计 {{ result.total }}</VChip>
          <VChip v-if="result.preview_success" color="success" variant="tonal">预览成功 {{ result.preview_success }}</VChip>
          <VChip v-if="result.completed" color="success" variant="tonal">已入库 {{ result.completed }}</VChip>
          <VChip v-if="result.accepted" color="info" variant="tonal">已接收 {{ result.accepted }}</VChip>
          <VChip v-if="result.failed" color="error" variant="tonal">失败 {{ result.failed }}</VChip>
          <VChip v-if="result.retry_wait" color="warning" variant="tonal">待重试 {{ result.retry_wait }}</VChip>
          <VChip v-if="result.manual_review" color="warning" variant="tonal">待复核 {{ result.manual_review }}</VChip>
          <VChip v-if="result.skipped" variant="tonal">跳过 {{ result.skipped }}</VChip>
        </div>
        <VTable v-if="result.items?.length" density="comfortable" class="manual-page__table">
          <thead>
            <tr>
              <th>状态</th>
              <th>源文件</th>
              <th>目标</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(item, index) in result.items" :key="`${item.source || index}-${index}`">
              <td><VChip size="small" :color="statusColor(item)" variant="tonal">{{ statusText(item) }}</VChip></td>
              <td class="manual-page__path-cell">{{ item.source || '-' }}</td>
              <td class="manual-page__path-cell">{{ item.target || item.target_dir || '-' }}</td>
              <td>{{ item.message || '-' }}</td>
            </tr>
          </tbody>
        </VTable>
      </VCardText>
    </VCard>

    <VDialog v-model="confirmOpen" max-width="34rem">
      <VCard title="确认开始整理">
        <VCardText>
          将调用 MoviePilot 原生“重新整理”，命中成功历史时会清理旧目标后重新入库。请确认来源地址和目录规则无误。
        </VCardText>
        <VCardActions>
          <VSpacer />
          <VBtn variant="text" @click="confirmOpen = false">取消</VBtn>
          <VBtn color="primary" @click="confirmOpen = false; invoke('organize')">确认整理</VBtn>
        </VCardActions>
      </VCard>
    </VDialog>
  </div>
</template>

<style scoped>
.manual-page {
  width: 100%;
  max-width: 1180px;
  margin: 0 auto;
  padding: 16px;
}

.manual-page__card,
.manual-page__result {
  border-radius: 16px;
}

.manual-page__section {
  min-height: 150px;
}

.manual-page__source-summary,
.manual-page__result-paths {
  display: grid;
  gap: 8px;
  word-break: break-word;
}

.manual-page__source-summary span,
.manual-page__result-paths span {
  color: rgb(var(--v-theme-on-surface-variant));
}

.manual-page__actions {
  justify-content: flex-end;
  gap: 8px;
  padding: 0 20px 18px;
}

.manual-page__path,
.manual-page__path-cell {
  word-break: break-all;
}

.manual-page__table {
  overflow-x: auto;
}

@media (max-width: 600px) {
  .manual-page {
    padding: 8px;
  }

  .manual-page__actions {
    flex-direction: column-reverse;
  }

  .manual-page__actions :deep(.v-btn) {
    width: 100%;
  }
}
</style>
