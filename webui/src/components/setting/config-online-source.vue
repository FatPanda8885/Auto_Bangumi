<script lang="ts" setup>
import type { OnlineSource } from '#/config';
import type { SettingItem } from '#/components';

const { t } = useMyI18n();
const message = useMessage();
const { getSettingGroup } = useConfigStore();
const { openModal } = useOnlineSourceStore();

const onlineSource = getSettingGroup('online_source');

const importUrl = ref('');
const importing = ref(false);

const items: SettingItem<OnlineSource>[] = [
  {
    configKey: 'enable',
    label: () => t('config.online_source_set.enable'),
    type: 'switch',
  },
  {
    configKey: 'aria2_rpc_url',
    label: () => t('config.online_source_set.aria2_rpc_url'),
    type: 'input',
    prop: { type: 'text', placeholder: 'http://172.17.0.1:6800' },
  },
  {
    configKey: 'aria2_secret',
    label: () => t('config.online_source_set.aria2_secret'),
    type: 'input',
    prop: { type: 'password', autocomplete: 'off' },
  },
  {
    configKey: 'save_path',
    label: () => t('config.online_source_set.save_path'),
    type: 'input',
    prop: { type: 'text', placeholder: '/downloads/Bangumi' },
  },
  {
    configKey: 'ffmpeg_path',
    label: () => t('config.online_source_set.ffmpeg_path'),
    type: 'input',
    prop: { type: 'text', placeholder: 'ffmpeg' },
  },
  {
    configKey: 'request_delay',
    label: () => t('config.online_source_set.request_delay'),
    type: 'input',
    prop: { type: 'text', placeholder: '2.0' },
  },
];

async function handleImport() {
  if (!importUrl.value.trim()) return;
  importing.value = true;
  try {
    const res = await apiOnlineSource.importSources(importUrl.value.trim());
    message.success(
      t('config.online_source_set.import_success', { count: res.imported })
    );
  } catch {
    message.error(t('config.online_source_set.import_failed'));
  } finally {
    importing.value = false;
  }
}
</script>

<template>
  <ab-fold-panel :title="$t('config.online_source_set.title')">
    <div space-y-8>
      <ab-setting
        v-for="i in items"
        :key="i.configKey"
        v-bind="i"
        v-model:data="onlineSource[i.configKey]"
      ></ab-setting>

      <div class="import-row">
        <ab-input
          v-model="importUrl"
          class="import-input"
          :placeholder="$t('config.online_source_set.import_url')"
        />
        <ab-button :loading="importing" @click="handleImport">
          {{ $t('config.online_source_set.import_btn') }}
        </ab-button>
      </div>

      <ab-button variant="primary" @click="openModal">
        {{ $t('config.online_source_set.search_open') }}
      </ab-button>
    </div>
  </ab-fold-panel>
</template>

<style lang="scss" scoped>
.import-row {
  display: flex;
  gap: 8px;
}

.import-input {
  flex: 1;
}
</style>
