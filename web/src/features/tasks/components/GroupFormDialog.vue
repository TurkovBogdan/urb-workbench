<script setup lang="ts">
// Карточка группы: название, описание, оформление и позиция в списке. Одно окно на создание и на
// правку — как у пространства: поля общие, различие ровно в заголовке и вызываемой ручке.
//
// Пространство в форме не выбирают: группа заводится в ТЕКУЩЕМ (его код приходит пропом), а правка
// его не принимает вовсе — перенос группы утащил бы за собой все её задачи.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
import { errorText } from '@/api/errorText'

import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'
import { createGroup, updateGroup, type GroupBody, type GroupRow } from '../api'
import { TASK_DESCRIPTION_MAX, TASK_TITLE_MAX } from '../labels'

/** Умолчание позиции повторяет `constants.py::SORT_DEFAULT` — середина шкалы. */
const SORT_DEFAULT = 500

const open = defineModel<boolean>({ required: true })

const props = defineProps<{
  /** Пространство, в котором заводится группа. При правке не используется. */
  workspace: string
  /** Правка существующей группы; `null` — создание. */
  group: GroupRow | null
}>()

const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()

const icons = iconNames()
const colors = colorNames()

const title = ref('')
const description = ref('')
const icon = ref<string | null>(null)
const color = ref<string | null>(null)
const sort = ref<number>(SORT_DEFAULT)
const saving = ref(false)
const error = ref<string | null>(null)

const creating = computed(() => props.group === null)

// Пустое название не сохраняется: без имени группа неразличима в списке. Пробелы бэк срежет до
// проверки длины — значит и здесь строка из одних пробелов считается пустой.
const valid = computed(() => title.value.trim().length > 0)

watch(() => [open.value, props.group] as const, ([isOpen, group]) => {
  if (!isOpen) return
  title.value = group?.title ?? ''
  description.value = group?.description ?? ''
  icon.value = group?.icon || null
  color.value = group?.color || null
  sort.value = group?.sort ?? SORT_DEFAULT
  error.value = null
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  const body: GroupBody = {
    title: title.value.trim(),
    description: description.value.trim(),
    color: color.value ?? '',
    icon: icon.value ?? '',
    sort: Number(sort.value) || SORT_DEFAULT,
  }
  try {
    // `report: false` — отказ показываем ЗДЕСЬ, рядом с кнопкой: окно остаётся открытым с
    // введённым текстом, а тост увёл бы сообщение из поля зрения.
    await (props.group
      ? updateGroup(props.group.code, body, { report: false })
      : createGroup(props.workspace, body, { report: false }))
    open.value = false
    emit('saved')
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
    :title="creating ? t('tasks.group.form.create_title') : t('tasks.group.form.title')"
    :description="props.group?.code"
    size="base"
    :persistent="saving"
    :close-disabled="saving"
  >
    <div class="group-form">
      <VTextField
        v-model="title"
        :label="t('tasks.group.form.name')"
        :maxlength="TASK_TITLE_MAX"
        variant="outlined"
        hide-details
        autofocus
      />

      <VTextarea
        v-model="description"
        :label="t('tasks.group.form.description')"
        :maxlength="TASK_DESCRIPTION_MAX"
        variant="outlined"
        rows="2"
        hide-details
      />

      <!-- Позиция — число, а не перетаскивание: групп в пространстве единицы, и ради их порядка
           заводить сортируемый список рано. Больший `sort` стоит выше. -->
      <VNumberInput
        v-model="sort"
        :label="t('tasks.group.form.sort')"
        :min="0"
        :step="10"
        control-variant="stacked"
        variant="outlined"
        hide-details
        inset
      />

      <div class="group-form__field">
        <span class="group-form__label">{{ t('tasks.group.form.look') }}</span>
        <IconColorPicker
          v-model:icon="icon"
          v-model:color="color"
          :icons="icons"
          :colors="colors"
          :resolve-icon="iconByName"
          :resolve-color="colorVarsByName"
          :height="160"
          clearable
        />
      </div>

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
.group-form {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

/* Подпись прижата к своему полю теснее, чем поля друг к другу, — иначе она читается как
   заголовок всего блока, а не как метка пикера. */
.group-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 4px;
}

.group-form__label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
