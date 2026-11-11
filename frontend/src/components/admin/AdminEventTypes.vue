<template>
    <!-- 活動類型 (ER-US-I05) -->
    <AdminCatalog endpoint="/admin/event-types" noun="活動類型"
                  hint="停用的類型不會出現在建立活動的選單中，既有活動維持原類型。已被活動使用的類型只能停用，不能刪除。" />
</template>

<script setup>
    import AdminCatalog from './AdminCatalog.vue'
</script>
