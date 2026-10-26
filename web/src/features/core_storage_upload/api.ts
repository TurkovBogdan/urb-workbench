/**
 * The file upload module (backend: `core_storage_upload`, `/storage/upload`) has no pages of its
 * own. Sending a file is the foundation's `@/api/upload` — every feature that holds files uses it,
 * and a feature does not import another one. The folder keeps the module shape so the module's
 * error dictionary in `locales/` has a home: its refusal codes `core_storage_upload.<entity>.<reason>`
 * are looked up in it.
 */

export {}
