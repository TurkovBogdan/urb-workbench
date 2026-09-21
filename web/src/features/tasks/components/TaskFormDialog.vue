<script setup lang="ts">
// Карточка задачи: одно окно на создание и на правку — поля и проверки у них общие, а различие
// ровно в вызываемых ручках. Режим задаёт проп: `task === null` — создание.
//
// Форма ведёт СВОЮ копию значений и синхронизируется при открытии: правка не должна менять
// карточку в списке до сохранения, а отмена обязана оставлять список нетронутым.
//
// Статус в форме есть, но уезжает он ОТДЕЛЬНЫМ запросом (`setTaskStatus`): общая правка статус
// не принимает — только своя ручка ставит отметки времени начала, завершения и отмены. При
// создании он едет вместе с карточкой: отметку там ставить ещё не по чему.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import { errorText } from '@/api/errorText'

import {
  createTask,
  getTask,
  listGroups,
  setTaskStatus,
  updateTask,
  type GroupRow,
  type TaskDetail,
  type TaskListRow,
} from '../api'
import { formatDeadline, parseDay } from '../dates'
import {
  BODY_MAX,
  TASK_CONSTRAINTS_MAX,
  TASK_CONTEXT_MAX,
  TASK_CRITERIA_MAX,
  TASK_DESCRIPTION_MAX,
  TASK_STATUSES,
  TASK_TITLE_MAX,
  TASK_TYPES,
  typeLayout,
} from '../labels'
import TaskPrioritySelect from './TaskPrioritySelect.vue'

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Пространство, в котором заводится задача: от него же зависит список групп. */
  workspace: string
  /** Правка существующей задачи; `null` — создание. */
  task: TaskDetail | TaskListRow | null
  /** Родитель создаваемой подзадачи; при правке не используется — перенос это другая операция. */
  parent?: TaskListRow | TaskDetail | null
}>()

const emit = defineEmits<{ saved: [code: string] }>()

const { t } = useI18n()

const title = ref('')
const description = ref('')
const context = ref('')
const constraints = ref('')
const criteria = ref('')
const body = ref('')
const type = ref<string>(TASK_TYPES[0])
const status = ref<string>(TASK_STATUSES[0])
const priority = ref<string>('normal')
const groupCode = ref<string | null>(null)
const deadlineAt = ref<Date | null>(null)

const saving = ref(false)
// Тело задачи ещё едет: из списка карточка приходит БЕЗ него (строка списка тела не несёт), а
// правка — полная замена карточки. Сохрани форма пустое тело, которого она не загружала, — текст
// задачи стёрся бы молча. Поэтому на время догрузки кнопка сохранения заперта.
const loadingBody = ref(false)
const error = ref<string | null>(null)

const groups = ref<GroupRow[]>([])

const creating = computed(() => props.task === null)

// Счётчик показывает ОСТАТОК, а не набранное: вопрос у человека всегда «сколько ещё влезет».
const titleLeft = computed(() => TASK_TITLE_MAX - title.value.length)
const descriptionLeft = computed(() => TASK_DESCRIPTION_MAX - description.value.length)

// Пустой заголовок не сохраняется: без него строка неразличима в списке. Пробелы бэк срежет до
// проверки длины — значит и здесь строка из одних пробелов считается пустой.
const valid = computed(() => title.value.trim().length > 0 && !loadingBody.value)

const typeItems = computed(() =>
  TASK_TYPES.map((value) => ({ value, title: t(`tasks.task.type.${value}`) })),
)
const statusItems = computed(() =>
  TASK_STATUSES.map((value) => ({ value, title: t(`tasks.task.status.${value}`) })),
)
const groupItems = computed(() =>
  groups.value.map((group) => ({ value: group.code, title: group.title })),
)

// Что показывает форма при выбранном типе. Скрытое поле продолжает ехать на бэк со своим прежним
// значением: переключение типа прячет, но не стирает — то же правило, что и на странице задачи.
const layout = computed(() => typeLayout(type.value))

async function loadGroups() {
  if (!props.workspace) {
    groups.value = []
    return
  }
  try {
    // `report: false` — справочник едет фоном под полем; тост о нём человек не связал бы с тем,
    // что делает. Пустой список групп честнее: задача проживёт и без группы.
    groups.value = await listGroups({ workspace: props.workspace }, { report: false })
  } catch {
    groups.value = []
  }
}

/** Разложить карточку по полям формы. Тексты берутся только у полной задачи — см. `loadingBody`. */
function apply(task: TaskDetail | TaskListRow | null) {
  title.value = task?.title ?? ''
  description.value = task?.description ?? ''
  type.value = task?.type ?? TASK_TYPES[0]
  status.value = task?.status ?? TASK_STATUSES[0]
  priority.value = task?.priority ?? 'normal'
  groupCode.value = task?.group_code ?? null
  deadlineAt.value = parseDay(task?.deadline_at ?? null)
  if (task && 'body' in task) applyTexts(task)
}

/** Длинные тексты карточки: постановка и план. Форма их не показывает, но обязана сохранить. */
function applyTexts(task: TaskDetail) {
  context.value = task.context
  constraints.value = task.constraints
  criteria.value = task.criteria
  body.value = task.body
}

watch(() => [open.value, props.task] as const, async ([isOpen, task]) => {
  if (!isOpen) return
  error.value = null
  context.value = ''
  constraints.value = ''
  criteria.value = ''
  body.value = ''
  apply(task)
  void loadGroups()
  // Из списка приходит строка без длинных текстов — дочитываем задачу целиком, иначе полная
  // замена карточки отправила бы пустую постановку вместо написанной. Из ответа берём ТОЛЬКО
  // тексты: остальные поля человек за это время мог уже начать править, и перезаписать их значило
  // бы стереть набранное.
  if (!task || 'body' in task) return
  loadingBody.value = true
  try {
    applyTexts(await getTask(task.code, { report: false }))
  } catch (e) {
    error.value = errorText(e)
  } finally {
    loadingBody.value = false
  }
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  try {
    // `report: false` — отказ операции показываем ЗДЕСЬ, рядом с кнопкой: окно остаётся открытым
    // с введённым текстом, а тост увёл бы сообщение из поля зрения.
    if (props.task) {
      let saved = await updateTask(
        props.task.code,
        {
          title: title.value.trim(),
          description: description.value.trim(),
          context: context.value,
          constraints: constraints.value,
          criteria: criteria.value,
          body: body.value,
          type: type.value,
          priority: priority.value,
          group_code: groupCode.value,
          deadline_at: formatDeadline(deadlineAt.value),
        },
        { report: false },
      )
      // Вторым запросом и только при смене: статус меняет ручка, которая ставит отметку фазы, и
      // звать её на каждом сохранении значило бы отмечать начало работы на правке опечатки.
      if (status.value !== props.task.status) {
        saved = await setTaskStatus(props.task.code, status.value, { report: false })
      }
      open.value = false
      emit('saved', saved.code)
    } else {
      const saved = await createTask(
        {
          workspace: props.workspace,
          title: title.value.trim(),
          description: description.value.trim(),
          context: context.value,
          constraints: constraints.value,
          criteria: criteria.value,
          body: body.value,
          type: type.value,
          status: status.value,
          priority: priority.value,
          group_code: groupCode.value,
          parent_code: props.parent?.code ?? null,
          deadline_at: formatDeadline(deadlineAt.value),
        },
        { report: false },
      )
      open.value = false
      emit('saved', saved.code)
    }
  } catch (e) {
    error.value = errorText(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <AppDialog
    v-model="open"
    :title="creating ? t('tasks.task.form.create_title') : t('tasks.task.form.title')"
    :description="props.parent && creating ? t('tasks.task.form.under', { title: props.parent.title }) : props.task?.code"
    size="base"
    scrollable
    :persistent="saving"
    :close-disabled="saving"
  >
    <!-- Порядок полей — от «что это» к «когда»: заголовок и описание, затем разметка (тип,
         статус, приоритет, группа), затем сроки, и последним длинное тело. -->
    <div class="task-form">
      <VTextField
        v-model="title"
        :label="t('tasks.task.form.name')"
        :maxlength="TASK_TITLE_MAX"
        :hint="t('tasks.task.form.left', { count: titleLeft })"
        variant="outlined"
        persistent-hint
        autofocus
      />

      <VTextarea
        v-model="description"
        :label="t('tasks.task.form.description')"
        :maxlength="TASK_DESCRIPTION_MAX"
        :hint="t('tasks.task.form.left', { count: descriptionLeft })"
        variant="outlined"
        rows="2"
        auto-grow
        persistent-hint
      />

      <!-- Тип стоит ДО длинных полей: он решает, какие из них вообще показаны, и выбирать его
           после того, как форма развернулась во весь экран, значило бы переставлять поля под
           курсором. Написанное при переключении остаётся — прячется только показ. -->
      <div class="task-form__field">
        <span class="task-form__label">{{ t('tasks.task.form.type') }}</span>
        <VBtnToggle v-model="type" mandatory density="default" variant="tonal" class="task-form__toggle">
          <VBtn v-for="item in typeItems" :key="item.value" :value="item.value">
            {{ item.title }}
          </VBtn>
        </VBtnToggle>
      </div>

      <div class="task-form__row">
        <VSelect
          v-model="status"
          :items="statusItems"
          :label="t('tasks.task.form.status')"
          :chips="false"
          variant="outlined"
          hide-details
        />
        <TaskPrioritySelect
          v-model="priority"
          :label="t('tasks.task.form.priority')"
          variant="outlined"
          hide-details
        />
      </div>

      <!-- Группа необязательна: задача без неё попадает в секцию «Без группы», а не теряется. -->
      <VSelect
        v-model="groupCode"
        :items="groupItems"
        :label="t('tasks.task.form.group')"
        :placeholder="t('tasks.task.form.no_group')"
        :chips="false"
        variant="outlined"
        clearable
        hide-details
      />

      <!-- Срок — единственная назначаемая дата: до какого числа успеть. Выбранный день уезжает
           последней секундой суток (`formatDeadline`). -->
      <VDateInput
        v-model="deadlineAt"
        :label="t('tasks.task.form.deadline_at')"
        variant="outlined"
        clearable
      />

      <!-- Пока длинные тексты не дочитаны, поля заперты: пустая рамка, в которую можно писать,
           выглядела бы как «текста нет», хотя он есть и сейчас приедет. -->
      <VTextarea
        v-model="context"
        :label="t('tasks.task.form.context')"
        :hint="t('tasks.task.form.context_hint')"
        :maxlength="TASK_CONTEXT_MAX"
        :disabled="loadingBody"
        :loading="loadingBody"
        variant="outlined"
        rows="4"
        auto-grow
        persistent-hint
      />

      <!-- Границы, критерии и план показываются с типа `standard`: у простой задачи их нет, и
           пустые поля растянули бы форму на экран, ничего не спросив. -->
      <template v-if="layout.brief">
        <VTextarea
          v-model="constraints"
          :label="t('tasks.task.form.constraints')"
          :hint="t('tasks.task.form.constraints_hint')"
          :maxlength="TASK_CONSTRAINTS_MAX"
          :disabled="loadingBody"
          variant="outlined"
          rows="3"
          auto-grow
          persistent-hint
        />

        <VTextarea
          v-model="criteria"
          :label="t('tasks.task.form.criteria')"
          :hint="t('tasks.task.form.criteria_hint')"
          :maxlength="TASK_CRITERIA_MAX"
          :disabled="loadingBody"
          variant="outlined"
          rows="3"
          auto-grow
          persistent-hint
        />
      </template>

      <VTextarea
        v-if="layout.plan"
        v-model="body"
        :label="t('tasks.task.form.body')"
        :hint="t('tasks.task.form.body_hint')"
        :maxlength="BODY_MAX"
        :disabled="loadingBody"
        :loading="loadingBody"
        variant="outlined"
        rows="5"
        auto-grow
        persistent-hint
      />

      <VAlert v-if="error" type="error" variant="tonal" density="compact">{{ error }}</VAlert>
    </div>

    <template #actions>
      <VBtn variant="text" :disabled="saving" @click="open = false">
        {{ t('common.action.cancel') }}
      </VBtn>
      <VBtn color="primary" variant="flat" :loading="saving" :disabled="!valid" @click="save">
        {{ creating ? t('common.action.add') : t('common.action.save') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* У части полей висит постоянная подсказка со счётчиком, поэтому шаг между ними меньше
   обычного: собственный отступ подсказки уже разделяет их. */
.task-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Два поля в ряд: они про одно и то же (разметка задачи, сроки) и порознь растянули бы окно
   вдвое. Ниже 520px ряд распадается — на узком экране половинка поля нечитаема. */
.task-form__row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

@media (max-width: 520px) {
  .task-form__row { grid-template-columns: 1fr; }
}

/* Подпись прижата к своему полю теснее, чем поля друг к другу, — иначе она читается как
   заголовок всего блока, а не как метка переключателя. */
.task-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.task-form__label {
  font-size: 12px;
  color: var(--text-muted);
}

/* Размер у группы кнопок не наследуется детьми (docs/conventions/frontend.md), а высота 40px
   уравнивает переключатель с соседними полями в рамке. */
.task-form__toggle { width: 100%; }
.task-form__toggle :deep(.v-btn) { flex: 1; height: 40px; font-size: 0.875rem; }
</style>
