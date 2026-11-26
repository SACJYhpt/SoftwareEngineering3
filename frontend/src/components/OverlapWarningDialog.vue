<template>
    <!-- 同單位活動時間重疊提醒對話框 (ER-US-C11)：只提醒，不阻擋儲存 -->
    <div v-if="open" class="dialog-backdrop" role="presentation">
        <div class="dialog panel" role="dialog" aria-modal="true" aria-labelledby="overlap-dialog-title">
            <h2 id="overlap-dialog-title">同單位活動時間重疊提醒</h2>
            <p class="dialog-desc">
                此活動時間與同單位以下活動重疊。本提醒不會阻擋儲存，請確認人力安排無誤後再決定是否繼續儲存：
            </p>
            <ul class="overlap-list">
                <li v-for="item in conflicts" :key="item.id" class="overlap-item">
                    <strong class="overlap-name">{{ item.name }}</strong>
                    <span class="overlap-time muted">{{ formatRange(item.start_time, item.end_time) }}</span>
                </li>
            </ul>
            <div class="dialog-actions">
                <button class="btn btn-outline" type="button" :disabled="submitting" @click="$emit('cancel')">
                    返回修改
                </button>
                <button class="btn" type="button" :disabled="submitting" @click="$emit('confirm')">
                    {{ submitting ? '儲存中…' : '確認仍要儲存' }}
                </button>
            </div>
        </div>
    </div>
</template>

<script setup>
    import { formatRange } from '../format'

    defineProps({
        open: { type: Boolean, default: false },
        conflicts: { type: Array, default: () => [] },
        submitting: { type: Boolean, default: false },
    })

    defineEmits(['cancel', 'confirm'])
</script>

<style scoped>
    .dialog-backdrop {
        position: fixed;
        inset: 0;
        background: rgba(15, 23, 42, 0.5);
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 16px;
        z-index: 200;
    }
    .dialog {
        width: min(100%, 520px);
        max-height: 85vh;
        overflow-y: auto;
        margin: 0;
    }
    .dialog h2 {
        margin: 0 0 10px;
        font-size: 1.2rem;
    }
    .dialog-desc {
        margin: 0 0 12px;
    }
    .overlap-list {
        list-style: none;
        padding: 0;
        margin: 0 0 20px;
        display: grid;
        gap: 8px;
    }
    .overlap-item {
        padding: 10px 12px;
        border: 1px solid var(--border);
        border-radius: 6px;
        background: var(--bg);
        display: flex;
        flex-direction: column;
        gap: 2px;
    }
    .overlap-name {
        overflow-wrap: anywhere;
    }
    .overlap-time {
        font-size: 0.9rem;
    }
    .dialog-actions {
        display: flex;
        justify-content: flex-end;
        flex-wrap: wrap;
        gap: 10px;
    }
</style>
