<script setup lang="ts">
// Задачи текущего пространства: плотный список с панелью фильтров.
//
// Страница сама ничего не рисует, кроме шапки: строки показывает компонент ФОРМАТА, фильтры —
// своя панель. Формат при этом хранится значением в сторе, а его разметка живёт в отдельном
// компоненте (`FORMATS`): второй формат (доска) должен появиться строчкой в таблице ниже и новым
// файлом рядом, а не ветвлением посреди этой разметки.
//
// АДРЕС. Список живёт на `/tasks/list`, задача — на своей странице (`/tasks/task/TASK@…`), и клик
// по строке уводит туда. Набор фильтров в адрес не вынесен: это рабочая поза человека, и каждая
// буква в поиске писала бы запись в историю браузера.
import { computed, onActivated, onMounted, ref, watch, type Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { IconList, IconPlus, IconRefresh } from '@tabler/icons-vue'

import PageLayout from '@/layout/templates/PageLayout.vue'
import PageHeader from '@/layout/components/PageHeader.vue'
import SectionError from '@/components/SectionError.vue'

import GroupFormDialog from '../components/GroupFormDialog.vue'
import TaskFilters from '../components/TaskFilters.vue'
import TaskFormDialog from '../components/TaskFormDialog.vue'
import TaskListTable from '../components/TaskListTable.vue'
import { useTasksStore } from '../stores/tasks.store'
import { useWorkspaceContextStore } from '@/features/workspace/stores/workspace-context.store'
import type { TaskListFormat } from '../stores/tasks.store'
import type { GroupRow, TaskDetail, TaskListRow } from '../api'

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const store = useTasksStore()
const context = useWorkspaceContextStore()

// Форматы показа: значение в сторе → компонент и подпись кнопки. Вся ветка второго формата —
// одна строка здесь плюс сам компонент; ни шапка, ни фильтры, ни окно задачи о нём не узнают.
const FORMATS: { code: TaskListFormat; label: string; icon: Component; view: Component }[] = [
  { code: 'list', label: 'tasks.task.list.format.list', icon: IconList, view: TaskListTable },
]

const formatView = computed(
  () => (FORMATS.find((item) => item.code === store.format) ?? FORMATS[0]).view,
)

// Страница живёт в KeepAlive и между переходами не размонтируется: `onMounted` отрабатывает
// первый показ, `onActivated` — каждое возвращение, иначе список остался бы вчерашним.
onMounted(store.load)
onActivated(store.load)

const workspace = computed(() => context.currentWorkspace?.code ?? '')

// ── Переход к задаче ──────────────────────────────────────────────────────────

function taskPath(code: string): string {
  return `/tasks/task/${encodeURIComponent(code)}`
}

// Куда уходили со списка. Список лежит в KeepAlive и возвращается тем же, каким его оставили, —
// отметка на строке говорит, откуда человек пришёл обратно.
const lastOpened = ref<string | null>(null)

function openTask(code: string) {
  lastOpened.value = code
  void router.push(taskPath(code))
}

// Наследие модального окна: задачу открывал параметр запроса, и такие ссылки разосланы. Переводим
// их на адрес страницы ЗАМЕНОЙ — шаг «назад» из задачи должен вести туда, откуда человек пришёл по
// ссылке, а не на тот же список с параметром, который снова себя перенаправит.
watch(
  () => route.query.task,
  (value) => {
    if (typeof value !== 'string' || !value) return
    void router.replace(taskPath(value))
  },
  { immediate: true },
)

// ── Форма задачи ──────────────────────────────────────────────────────────────
// Создание и правка — одно окно: пустая карточка отличается от заполненной только тем, что
// задачи у неё пока нет. Форма одна на всю страницу, откуда бы её ни позвали — из строки списка
// или из карточки задачи: вторая копия разошлась бы с первой на первом же новом поле.
const editing = ref<TaskDetail | TaskListRow | null>(null)
const parent = ref<TaskDetail | TaskListRow | null>(null)
const formOpen = ref(false)

function create() {
  editing.value = null
  parent.value = null
  formOpen.value = true
}

function edit(task: TaskDetail | TaskListRow) {
  editing.value = task
  parent.value = null
  formOpen.value = true
}

function addChild(task: TaskDetail | TaskListRow) {
  editing.value = null
  parent.value = task
  formOpen.value = true
}

/**
 * Сохранение могло переставить что угодно — группу, статус, тело, — поэтому список перечитывается
 * целиком. Заведённая подзадача открывается сразу: её ради этого и заводили.
 */
function onSaved(code: string) {
  void store.load()
  if (parent.value) openTask(code)
}

// ── Форма группы ──────────────────────────────────────────────────────────────
// То же окно, что на странице групп, — правку зовут из шапки карточки в списке. Живёт оно здесь,
// а не внутри списка: окон на странице одно на сущность, и формат показа (доска будет второй) не
// должен возить их с собой.
const editingGroup = ref<GroupRow | null>(null)
const groupFormOpen = ref(false)

function editGroup(group: GroupRow) {
  editingGroup.value = group
  groupFormOpen.value = true
}
</script>

<template>
  <PageLayout>
    <PageHeader
      :title="t('tasks.task.list.title')"
      :description="t('tasks.task.list.description')"
    >
      <template #actions>
        <!-- Формат показа — не фильтр: он не сужает выдачу, а меняет то, как она нарисована,
             и место ему в шапке страницы, а не в панели фильтров. `mandatory` — снять формат
             нельзя, какой-то из них всегда включён. -->
        <VBtnToggle
          v-model="store.format"
          mandatory
          density="comfortable"
          variant="outlined"
          divided
          class="format-toggle"
        >
          <VBtn v-for="item in FORMATS" :key="item.code" :value="item.code" icon>
            <component :is="item.icon" :size="18" />
            <VTooltip activator="parent" location="top">{{ t(item.label) }}</VTooltip>
          </VBtn>
        </VBtnToggle>

        <VBtn variant="text" :disabled="store.loading" @click="store.load">
          <template #prepend><IconRefresh :size="16" :class="{ 'icon-spin': store.loading }" /></template>
          {{ t('tasks.action.refresh') }}
        </VBtn>
        <VBtn color="primary" variant="flat" :disabled="!workspace" @click="create">
          <template #prepend><IconPlus :size="16" /></template>
          {{ t('tasks.task.list.add') }}
        </VBtn>
      </template>
    </PageHeader>

    <SectionError v-if="store.error" :error="store.error" />

    <!-- Пространств нет вовсе: задачам негде лежать, и ни фильтры, ни таблица здесь ничего не
         значат — показывать их с пустыми списками значило бы предлагать сузить ничто. Ведём
         туда, где заводят пространство. -->
    <div v-else-if="store.noWorkspace" class="tasks-empty">
      <p class="tasks-empty__title">{{ t('tasks.task.list.no_workspace') }}</p>
      <p class="tasks-empty__hint">{{ t('tasks.task.list.no_workspace_hint') }}</p>
      <VBtn color="primary" variant="flat" to="/tasks/workspaces">
        {{ t('tasks.task.list.to_workspaces') }}
      </VBtn>
    </div>

    <!-- Поиск и фильтры — своя карточка НАД списком, одна на все форматы: они правят то, что
         показано, и принадлежат экрану, а не тому, кто рисует строки (та же анатомия, что у
         остальных страниц-списков — `filter-panel` + карточка содержимого под ней). -->
    <template v-else>
      <VCard variant="outlined" rounded="lg" class="filter-panel mb-3">
        <TaskFilters />
      </VCard>

      <component
        :is="formatView"
        :open-code="lastOpened"
        @open="openTask"
        @create="create"
        @edit="edit"
        @add-child="addChild"
        @edit-group="editGroup"
      />
    </template>

    <TaskFormDialog
      v-model="formOpen"
      :workspace="workspace"
      :task="editing"
      :parent="parent"
      @saved="onSaved"
    />

    <!-- Правка группы меняет и её карточку, и раскладку секций, поэтому список перечитывается
         целиком — тем же способом, что и после правки задачи. -->
    <GroupFormDialog
      v-model="groupFormOpen"
      :workspace="workspace"
      :group="editingGroup"
      @saved="store.load"
    />
  </PageLayout>
</template>

<style scoped>
/* Группа форматов идёт первой в ряду действий и отбита от него: она про вид страницы, а
   соседние кнопки — про её содержимое. */
.format-toggle { margin-right: 4px; }

/* Общая для страниц-списков рамка панели: 12px по кругу — ОДИН отступ на двоих, внутри панель
   своего не добавляет. Пока отступ держали оба, слева набегало 24px: вдвое больше, чем у
   заголовка страницы и у строк списка под ней, и панель выглядела сдвинутой вправо. */
.filter-panel { padding: 10px 12px; }

.tasks-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 200px;
  text-align: center;
}

.tasks-empty__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.tasks-empty__hint {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--text-muted);
}
</style>
