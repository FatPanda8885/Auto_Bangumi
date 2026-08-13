import type {
  OnlineChannel,
  OnlineSourceSummary,
  OnlineSubject,
} from '#/onlineSource';

export const useOnlineSourceStore = defineStore('onlineSource', () => {
  const sources = ref<OnlineSourceSummary[]>([]);

  // SSE 搜索流（keyword/source 由该组合式对象持有）
  const search = apiOnlineSource.search();
  const source = search.source;
  const keyword = search.keyword;
  const subjects = search.data;
  const searchFailed = search.error;
  const openSearchStream = search.open;
  const closeSearchStream = search.close;

  const showModal = ref(false);
  const selectedSubject = ref<OnlineSubject | null>(null);
  const channels = ref<OnlineChannel[]>([]);
  const loadingEpisodes = ref(false);

  const loading = computed(() => search.status.value !== 'CLOSED');

  async function loadSources() {
    sources.value = await apiOnlineSource.listSources();
    if (!source.value && sources.value.length) {
      source.value = sources.value[0].name;
    }
  }

  function openModal() {
    showModal.value = true;
    if (!sources.value.length) loadSources();
  }

  function closeModal() {
    showModal.value = false;
    selectedSubject.value = null;
    channels.value = [];
    closeSearchStream();
  }

  function onSearch() {
    if (!keyword.value.trim() || !source.value) return;
    openSearchStream();
  }

  async function selectSubject(subject: OnlineSubject) {
    selectedSubject.value = subject;
    loadingEpisodes.value = true;
    try {
      channels.value = await apiOnlineSource.getEpisodes(
        source.value,
        subject.url
      );
    } catch {
      channels.value = [];
    } finally {
      loadingEpisodes.value = false;
    }
  }

  function clearSelectedSubject() {
    selectedSubject.value = null;
    channels.value = [];
  }

  watch(keyword, (v) => {
    if (!v.trim()) closeSearchStream();
  });

  return {
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
    loadSources,
    openModal,
    closeModal,
    onSearch,
    selectSubject,
    clearSelectedSubject,
  };
});
