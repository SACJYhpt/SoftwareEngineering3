<template>
    <!-- 單位：系所、行政單位、社團 (ER-US-I06) -->
    <AdminCatalog endpoint="/admin/units" noun="單位" with-kind
                  hint="更名後，使用者資料與活動主辦單位同步顯示新名稱。停用的單位無法建立新活動，既有活動不受影響；被使用中的單位不能改變類型或刪除。" />
</template>

<script setup>
    import AdminCatalog from './AdminCatalog.vue'
</script>
