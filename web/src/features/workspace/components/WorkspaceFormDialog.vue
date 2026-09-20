<script setup lang="ts">
// Карточка пространства: название, описание, иконка и цвет. Одно окно на создание и на правку —
// поля и проверки у них общие, а различие ровно в двух местах (заголовок и вызываемая ручка),
// и второй компонент ради них означал бы две формы, расходящиеся при первой же новой колонке.
// Режим задаёт проп: `workspace === null` — создание.
//
// Анатомия окна (шапка, тело, полоса кнопок) приходит из AppDialog, здесь только поля. Форма
// ведёт СВОЮ копию значений и синхронизируется при открытии: правка не должна менять карточку
// в списке до сохранения, а отмена обязана оставлять список нетронутым.
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import AppDialog from '@/components/AppDialog.vue'
import IconColorPicker from '@/components/IconColorPicker.vue'
import { errorText } from '@/api/errorText'

import { colorNames, colorVarsByName } from '@/shared/colors'
import { iconByName, iconNames } from '@/shared/icons'
import { createWorkspace, updateWorkspace, type WorkspaceBody, type WorkspaceRow } from '../api'

// Потолки повторяют колонки БД (`workspace/constants.py`: TITLE_MAX / DESCRIPTION_MAX). Бэк длинное не
// примет (422), но узнать об этом после отправки — значит потерять набранное: поле само не даёт
// перебрать, а счётчик показывает, сколько ещё осталось.
const TITLE_MAX = 96
const DESCRIPTION_MAX = 512

const open = defineModel<boolean>({ required: true })

const props = defineProps<{ workspace: WorkspaceRow | null }>()
const emit = defineEmits<{ saved: [] }>()

const { t } = useI18n()

const icons = iconNames()
const colors = colorNames()

const title = ref('')
const description = ref('')
const icon = ref<string | null>(null)
const color = ref<string | null>(null)
const saving = ref(false)
const error = ref<string | null>(null)

const creating = computed(() => props.workspace === null)

// Счётчик показывает ОСТАТОК, а не набранное: вопрос у человека всегда «сколько ещё влезет».
const titleLeft = computed(() => TITLE_MAX - title.value.length)
const descriptionLeft = computed(() => DESCRIPTION_MAX - description.value.length)

// Пустое название не сохраняется: без имени карточка неразличима в списке. Пробелы бэк срежет
// до проверки длины — значит и здесь строка из одних пробелов считается пустой.
const valid = computed(() => title.value.trim().length > 0)

watch(() => [open.value, props.workspace] as const, ([isOpen, workspace]) => {
  if (!isOpen) return
  title.value = workspace?.title ?? ''
  description.value = workspace?.description ?? ''
  icon.value = workspace?.icon || null
  color.value = workspace?.color || null
  error.value = null
}, { immediate: true })

async function save() {
  if (!valid.value) return
  saving.value = true
  error.value = null
  const body: WorkspaceBody = {
    title: title.value.trim(),
    description: description.value.trim(),
    color: color.value ?? '',
    icon: icon.value ?? '',
  }
  try {
    // `report: false` — отказ операции показываем ЗДЕСЬ, рядом с кнопкой: окно остаётся
    // открытым с введённым текстом, а тост увёл бы сообщение из поля зрения.
    await (props.workspace
      ? updateWorkspace(props.workspace.code, body, { report: false })
      : createWorkspace(body, { report: false }))
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
    :title="creating ? t('workspace.form.create_title') : t('workspace.form.title')"
    :description="props.workspace?.code"
    size="base"
    :persistent="saving"
    :close-disabled="saving"
  >
    <!-- Порядок: что это (название, описание) → как выглядит (иконка и цвет). Пикер последний —
         он самый высокий, и над ним ничего не должно прыгать при прокрутке. -->
    <div class="workspace-form">
      <VTextField
        v-model="title"
        :label="t('workspace.form.name')"
        variant="outlined"
        :maxlength="TITLE_MAX"
        :hint="t('workspace.form.left', { count: titleLeft })"
        persistent-hint
        autofocus
      />

      <VTextarea
        v-model="description"
        :label="t('workspace.form.description')"
        variant="outlined"
        rows="2"
        auto-grow
        :maxlength="DESCRIPTION_MAX"
        :hint="t('workspace.form.left', { count: descriptionLeft })"
        persistent-hint
      />

      <div class="workspace-form__field">
        <span class="workspace-form__label">{{ t('workspace.form.look') }}</span>
        <!-- Предпросмотр плашки живёт внутри панели, рядом с палитрой: рисунок и цвет
             оценивают вместе, врозь выбирать их не по чему.
             Наборы имён — общие реестры фронта (`shared/colors.ts` / `shared/icons.ts`), те же,
             что у групп исследований: палитра одна на приложение, второй её копии быть не должно. -->
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
      <VBtn
        color="primary"
        variant="flat"
        :loading="saving"
        :disabled="!valid"
        @click="save"
      >
        {{ creating ? t('common.action.add') : t('common.action.save') }}
      </VBtn>
    </template>
  </AppDialog>
</template>

<style scoped>
/* У полей висит постоянная подсказка со счётчиком, поэтому шаг между ними меньше обычного:
   собственный отступ подсказки уже разделяет их. */
.workspace-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Подпись прижата к своему полю теснее, чем поля друг к другу, — иначе она читается как
   заголовок всего блока, а не как метка пикера. */
.workspace-form__field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-top: 8px;
}

.workspace-form__label {
  font-size: 12px;
  color: var(--text-muted);
}
</style>
