<script setup lang="ts">
// Stored pictures full screen, named by their codes — a files section's pictures, a text's gallery.
// Each code is read from its preview (address, title, description) in the page's scope and handed
// to the app's viewer (`ImageLightbox`), which pages through them in the order given; a code whose
// preview has not come yet, or says the file is gone, is left out until it does.
//
// `IMAGE@` and `FILE@` name the same stored file, and either is taken. The viewer's panel is given
// the picture's `IMAGE@`, and that is the form the v-model comes back in. Which codes are pictures
// the caller knows — a section by the file's type, a text by what it drew — and passes only those.
import { computed, watch } from 'vue'

import ImageLightbox, { type LightboxImage } from '@/components/ImageLightbox.vue'
import { usePreviews } from '@/stores/preview'

const props = defineProps<{
  /** The pictures to page through, in order. */
  codes: string[]
}>()

/** The picture on screen; `null` — closed. */
const current = defineModel<string | null>({ default: null })

const previews = usePreviews()

function asPicture(code: string): string {
  return `IMAGE@${code.slice(code.indexOf('@') + 1)}`
}

const pictures = computed(() => props.codes.map(asPicture))

watch(pictures, (codes) => previews.ensure(codes), { immediate: true })

const images = computed<LightboxImage[]>(() => pictures.value.flatMap((code) => {
  const record = previews.get(code)
  if (!record || record.error || !record.link) return []
  return [{ src: record.link, code, title: record.title, description: record.description }]
}))

// The viewer pages by address; the page speaks in codes.
const shown = computed<string | null>({
  get: () => {
    const code = current.value ? asPicture(current.value) : null
    return images.value.find((image) => image.code === code)?.src ?? null
  },
  set: (src) => {
    current.value = src ? images.value.find((image) => image.src === src)?.code ?? null : null
  },
})
</script>

<template>
  <ImageLightbox v-model="shown" :images="images" />
</template>
