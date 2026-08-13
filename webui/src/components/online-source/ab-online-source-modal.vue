<script lang="ts" setup>
import { Close } from '@icon-park/vue-next';
import { NSpin } from 'naive-ui';
import type { OnlineChannel, OnlineEpisode } from '#/onlineSource';

const { t } = useMyI18n();
const message = useMessage();

const {
  sources,
  source,
  keyword,
  loading,
  searchFailed,
  subjects,
  showModal,
  selectedSubject,
  channels,
  loadingEpisodes,
} = storeToRefs(useOnlineSourceStore());
const {
  loadSources,
  closeModal,
  onSearch,
  selectSubject,
  clearSelectedSubject,
} = useOnlineSourceStore();

const { activeBangumi, getAll } = useBangumiStore();

// 下载步骤局部状态
const selectedChannel = ref('');
const selectedEpisode = ref<OnlineEpisode | null>(null);
const targetBangumiId = ref<string | null>(null);
const season = ref(1);
const episode = ref(1);
const bindEnabled = ref(false);
const updateTime = ref('');
const updateWeekday = ref('');
const downloading = ref(false);
const binding = ref(false);

const sourceItems = computed(() => sources.value.map((s) => s.name));
const channelItems = computed(() => channels.value.map((c) => c.name));
const bangumiItems = computed(() =>
  activeBangumi.map((b) => ({
    id: b.id,
    value: String(b.id),
    label: b.official_title,
  }))
);
const weekdayItems = computed(() => [
  { id: 0, value: '', label: t('online_source.everyday') },
  { id: 1, value: '0', label: t('online_source.monday') },
  { id: 2, value: '1', label: t('online_source.tuesday') },
  { id: 3, value: '2', label: t('online_source.wednesday') },
  { id: 4, value: '3', label: t('online_source.thursday') },
  { id: 5, value: '4', label: t('online_source.friday') },
  { id: 6, value: '5', label: t('online_source.saturday') },
  { id: 7, value: '6', label: t('online_source.sunday') },
]);

const currentChannel = computed<OnlineChannel | null>(() => {
  if (!channels.value.length) return null;
  if (selectedChannel.value) {
    return (
      channels.value.find((c) => c.name === selectedChannel.value) ||
      channels.value[0]
    );
  }
  return channels.value.find((c) => c.episodes.length) || channels.value[0];
});
const currentEpisodes = computed(() => currentChannel.value?.episodes ?? []);

// 选中番剧后默认路线
watch(channels, (val) => {
  const first = val.find((c) => c.episodes.length) || val[0];
  selectedChannel.value = first?.name ?? '';
  selectedEpisode.value = null;
});

// 打开弹层时确保已加载番剧列表
watch(showModal, (val) => {
  if (val && !activeBangumi.length) getAll();
});

onMounted(() => {
  if (sources.value.length === 0) loadSources();
});

function onPickEpisode(ep: OnlineEpisode) {
  selectedEpisode.value = ep;
  season.value = 1;
  episode.value = ep.sort ?? 1;
  const target = activeBangumi[0];
  targetBangumiId.value = target ? String(target.id) : null;
}

function backToSearch() {
  clearSelectedSubject();
  selectedEpisode.value = null;
}

async function handleDownload() {
  if (!selectedEpisode.value || !targetBangumiId.value) return;
  downloading.value = true;
  try {
    const res = await apiOnlineSource.download({
      source: source.value,
      episode_url: selectedEpisode.value.url,
      bangumi_id: Number(targetBangumiId.value),
      season: season.value,
      episode: episode.value,
      media_type: 'episode',
    });
    if (res.status === 'added')
      message.success(t('online_source.download_success'));
    else if (res.status === 'duplicate')
      message.info(t('online_source.download_duplicate'));
    else message.error(t('online_source.download_failed'));
  } catch {
    message.error(t('online_source.download_failed'));
  } finally {
    downloading.value = false;
  }
}

async function handleBind() {
  if (!selectedSubject.value || !targetBangumiId.value) return;
  const target = activeBangumi.find(
    (b) => b.id === Number(targetBangumiId.value)
  );
  if (!target) return;
  binding.value = true;
  try {
    const updated = {
      ...target,
      online_source: source.value,
      online_subject_id: selectedSubject.value.url,
      online_channel: currentChannel.value?.name ?? null,
      online_update_time: bindEnabled.value
        ? updateTime.value.trim() || null
        : target.online_update_time,
      online_update_weekday:
        bindEnabled.value && updateWeekday.value !== ''
          ? Number(updateWeekday.value)
          : target.online_update_weekday,
    };
    await apiBangumi.updateRule(target.id, updated);
    message.success(t('online_source.bind_success'));
  } catch {
    message.error(t('online_source.bind_failed'));
  } finally {
    binding.value = false;
  }
}

function handleClose() {
  closeModal();
  selectedEpisode.value = null;
}
</script>

<template>
  <Teleport to="body">
    <transition name="overlay">
      <div v-if="showModal" class="modal-backdrop" @click.self="handleClose" />
    </transition>

    <transition name="modal">
      <div
        v-if="showModal"
        class="modal-container"
        role="dialog"
        aria-modal="true"
      >
        <div class="modal-content">
          <!-- Header -->
          <header class="modal-header">
            <h2 class="modal-title">{{ t('online_source.title') }}</h2>
            <ab-select
              v-model="source"
              :items="sourceItems"
              class="source-select"
              :aria-label="t('online_source.source')"
            />
            <ab-icon-button :label="t('common.close')" @click="handleClose">
              <Close theme="outline" size="18" />
            </ab-icon-button>
          </header>

          <!-- Search bar -->
          <div v-if="!selectedSubject" class="search-bar">
            <ab-input
              v-model="keyword"
              class="search-input"
              :placeholder="t('online_source.search_placeholder')"
            />
            <ab-button variant="primary" :loading="loading" @click="onSearch">
              {{ t('online_source.search') }}
            </ab-button>
          </div>

          <div class="content">
            <p v-if="sources.length === 0" class="hint">
              {{ t('online_source.no_sources') }}
            </p>

            <!-- Subject results -->
            <template v-else-if="!selectedSubject">
              <p v-if="searchFailed" class="hint">
                {{ t('online_source.failed') }}
              </p>
              <p
                v-else-if="!loading && subjects.length === 0 && keyword"
                class="hint"
              >
                {{ t('online_source.no_results') }}
              </p>
              <p v-else-if="!keyword" class="hint">
                {{ t('online_source.start_typing') }}
              </p>
              <ul v-else class="subject-list">
                <li v-for="s in subjects" :key="s.url">
                  <button class="subject-item" @click="selectSubject(s)">
                    {{ s.name }}
                  </button>
                </li>
              </ul>
            </template>

            <!-- Episode list -->
            <template v-else>
              <button class="back-btn" @click="backToSearch">
                {{ selectedSubject.name }}
              </button>
              <div v-if="loadingEpisodes" class="hint">
                <NSpin :size="20" />
              </div>
              <template v-else>
                <ab-select
                  v-if="channelItems.length > 1"
                  v-model="selectedChannel"
                  :items="channelItems"
                  class="channel-select"
                  :aria-label="t('online_source.channel')"
                />
                <div class="episode-list">
                  <button
                    v-for="ep in currentEpisodes"
                    :key="ep.url"
                    class="episode-item"
                    @click="onPickEpisode(ep)"
                  >
                    <span class="ep-sort">{{ ep.sort ?? '-' }}</span>
                    <span class="ep-name">{{ ep.name }}</span>
                  </button>
                </div>
              </template>
            </template>
          </div>

          <!-- Download panel -->
          <footer v-if="selectedEpisode" class="download-panel">
            <div class="download-row">
              <span class="dl-label">{{
                t('online_source.target_bangumi')
              }}</span>
              <ab-select
                v-model="targetBangumiId"
                :items="bangumiItems"
                class="bangumi-select"
              />
            </div>
            <div class="download-row">
              <span class="dl-label">{{ t('online_source.season') }}</span>
              <ab-input v-model="season" type="number" class="num-input" />
              <span class="dl-label">{{ t('online_source.episode') }}</span>
              <ab-input v-model="episode" type="number" class="num-input" />
            </div>

            <div class="download-row">
              <ab-button
                variant="primary"
                :loading="downloading"
                @click="handleDownload"
              >
                {{ t('online_source.download') }}
              </ab-button>
            </div>

            <div class="bind-section">
              <ab-switch v-model="bindEnabled" />
              <span class="dl-label">{{ t('online_source.bind') }}</span>
            </div>
            <template v-if="bindEnabled">
              <div class="download-row">
                <span class="dl-label">{{
                  t('online_source.update_time')
                }}</span>
                <ab-input
                  v-model="updateTime"
                  placeholder="22:00"
                  class="num-input"
                />
                <span class="dl-label">{{
                  t('online_source.update_weekday')
                }}</span>
                <ab-select
                  v-model="updateWeekday"
                  :items="weekdayItems"
                  class="weekday-select"
                />
              </div>
              <div class="download-row">
                <ab-button :loading="binding" @click="handleBind">
                  {{ t('online_source.bind_confirm') }}
                </ab-button>
              </div>
            </template>
          </footer>
        </div>
      </div>
    </transition>
  </Teleport>
</template>

<style lang="scss" scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: var(--color-overlay);
  z-index: var(--z-modal-backdrop);
}

.modal-container {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: flex-start;
  justify-content: center;
  padding: 60px 16px 16px;
  z-index: var(--z-modal);
  overflow-y: auto;
}

.modal-content {
  width: 100%;
  max-width: 640px;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-bottom: 1px solid var(--color-border);
}

.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0;
  flex: 1;
  min-width: 0;
}

.source-select {
  width: 160px;
  flex-shrink: 0;
}

.search-bar {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}

.search-input {
  flex: 1;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  min-height: 200px;
}

.hint {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  color: var(--color-text-muted);
  font-size: 14px;
}

.subject-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.subject-item {
  display: block;
  width: 100%;
  padding: 12px 14px;
  text-align: left;
  font-size: 14px;
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: border-color var(--transition-fast);

  &:hover,
  &:focus-visible {
    border-color: var(--color-primary);
    color: var(--color-primary);
  }
}

.back-btn {
  display: block;
  width: 100%;
  margin-bottom: 12px;
  padding: 8px 0;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  color: var(--color-primary);
  background: transparent;
  border: none;
  cursor: pointer;
  text-align: left;
}

.channel-select {
  margin-bottom: 12px;
}

.episode-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.episode-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  font-family: inherit;
  background: var(--color-surface-hover);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  cursor: pointer;
  text-align: left;
  transition: border-color var(--transition-fast);

  &:hover,
  &:focus-visible {
    border-color: var(--color-primary);
  }
}

.ep-sort {
  width: 40px;
  flex-shrink: 0;
  font-variant-numeric: tabular-nums;
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--color-text-muted);
}

.ep-name {
  font-size: 14px;
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.download-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  border-top: 1px solid var(--color-border);
  background: var(--color-surface-hover);
}

.download-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.dl-label {
  flex-shrink: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.bangumi-select {
  flex: 1;
  min-width: 0;
}

.num-input {
  width: 70px;
}

.weekday-select {
  flex: 1;
  min-width: 0;
}

.bind-section {
  display: flex;
  align-items: center;
  gap: 8px;
}

// transition
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-normal),
    transform var(--transition-normal);
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
  transform: translateY(-10px) scale(0.98);
}
</style>
