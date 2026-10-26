<script setup lang="ts">
// The menu a right click opens on a shown picture — a lone one or one of a gallery, in the viewer
// and in an editor field alike: copy its code, copy the picture itself, open it full screen, open
// it in a tab, download it; in a field take it out of the text; and where the page's entity holds
// the file, delete the file.
//
// The app's one action menu (`ActionMenu`), without a "⋯" of its own: a picture in a text has no
// row to hold a button. "Copy code" comes first, as in every menu with a code, and copying the
// picture right after it (`files/copyImage.ts`); what changes something comes last, set apart. Two
// deletions, and the items say which: "from the text" only takes this picture out of the text, the
// file stays; "the file" takes the file out of the page's entity and asks first, as deleting in the
// files section does. Technically it only cuts the entity's link to the file: the storage marks the
// file deleted once no live owner is left, and its cleanup removes it later — until then attaching
// it again brings it back. It goes through the page's file editor (`FILE_BINDING_EDITOR`), so it is
// offered only where the page's own entity holds the file and the entity is not in the trash — the
// same rule the media panel edits a title by.
//
// What the picture is — its address, name and type — is read from its preview by the code.
import { computed, inject, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { IconArrowsMaximize, IconClipboardCopy, IconDownload, IconExternalLink, IconEraser, IconTrash } from '@tabler/icons-vue'

import { errorText } from '@/api/errorText'
import ActionMenu, { type ActionMenuItem } from '@/components/ActionMenu.vue'
import ConfirmDialog from '@/components/ConfirmDialog.vue'
import { copyImage } from '@/components/files/copyImage'
import { downloadHref, downloadName, startDownload } from '@/components/files/download'
import { FILE_BINDING_EDITOR } from '@/components/files/fileBinding'
import { pushToast } from '@/composables/useToasts'
import { usePreviews } from '@/stores/preview'

const props = defineProps<{
  /** The picture's `IMAGE@` code; empty while no picture is aimed at. */
  code: string
  /** Take the picture out of the text; unset — the text is read, not edited. */
  remove?: () => void
}>()

const emit = defineEmits<{
  /** Open it full screen, with its gallery — the zone knows the gallery. */
  open: []
  /** The file is deleted: an editor field takes the picture out of its text too. */
  deleted: []
}>()

const { t } = useI18n()
const previews = usePreviews()
const fileEditor = inject(FILE_BINDING_EDITOR, null)

const record = computed(() => (props.code ? previews.get(props.code) : undefined))
const deletable = computed(() => Boolean(record.value?.held && fileEditor && !fileEditor.readonly()))

const items = computed<ActionMenuItem[]>(() => {
  const link = record.value?.link ?? ''
  const name = downloadName(record.value?.title ?? '')
  const list: ActionMenuItem[] = [
    { key: 'copy-content', icon: IconClipboardCopy, label: t('common.picture_menu.copy_content'), run: () => copyContent(link) },
    { key: 'open', icon: IconArrowsMaximize, label: t('common.picture_menu.open'), hotkey: 'E', run: () => emit('open') },
    { key: 'open-tab', icon: IconExternalLink, label: t('common.picture_menu.open_tab'), hotkey: 'T', run: () => window.open(link, '_blank', 'noopener') },
    { key: 'download', icon: IconDownload, label: t('common.picture_menu.download'), run: () => startDownload(downloadHref(link, name), name) },
  ]
  const remove = props.remove
  if (remove) {
    list.push({ key: 'remove', icon: IconEraser, label: t('common.picture_menu.remove'), danger: true, hotkey: 'D', divider: true, run: remove })
  }
  if (deletable.value) {
    list.push({ key: 'delete-file', icon: IconTrash, label: t('common.picture_menu.delete_file'), danger: true, divider: !remove, run: ask })
  }
  return list
})

const menu = ref<InstanceType<typeof ActionMenu> | null>(null)
const open = defineModel<boolean>('open', { default: false })

/** Open at the right click's point. */
function openAt(event: MouseEvent): boolean {
  return menu.value?.openAt(event) ?? false
}

// ── Copying the picture ───────────────────────────────────────────────────────
// The menu closes on the click, so the outcome is said by a toast — there is no item left to mark.
async function copyContent(link: string): Promise<void> {
  try {
    await copyImage(link)
    pushToast(t('common.picture_menu.content_copied'), 'success')
  } catch {
    pushToast(t('common.picture_menu.content_not_copied'), 'error')
  }
}

// ── Deleting the file ─────────────────────────────────────────────────────────
// The name is taken when asked: the dialog keeps its text while it fades out.
const confirmOpen = ref(false)
const asking = ref<{ code: string; name: string } | null>(null)

function ask(): void {
  asking.value = { code: props.code, name: record.value?.title || props.code }
  confirmOpen.value = true
}

async function deleteFile(): Promise<void> {
  confirmOpen.value = false
  const target = asking.value
  if (!target || !fileEditor) return
  // The holder's list speaks of the file as `FILE@`, whatever word the text shows it by.
  const file = `FILE@${target.code.split('@').pop() ?? ''}`
  try {
    await fileEditor.remove(file)
  } catch (error) {
    pushToast(errorText(error))
    return
  }
  emit('deleted')
}

const confirmText = computed(() => t('common.picture_menu.delete_confirm.text', { name: asking.value?.name ?? '' }))

defineExpose({ openAt })
</script>

<template>
  <ActionMenu
    ref="menu"
    v-model:open="open"
    :items="items"
    :code="props.code"
    :label="t('common.picture_menu.label')"
    pointer-only
  />
  <ConfirmDialog
    v-model="confirmOpen"
    :title="t('common.picture_menu.delete_confirm.title')"
    :text="confirmText"
    :confirm-label="t('common.picture_menu.delete_confirm.confirm')"
    enter-confirms
    focus-confirm
    @confirm="deleteFile"
  />
</template>
