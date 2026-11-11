<template><main class="page narrow"><section class="panel"><h1>信箱驗證</h1><p v-if="busy" class="muted">正在驗證…</p><p v-else :class="['alert', ok ? 'alert-ok' : 'alert-error']">{{ message }}</p><router-link v-if="ok" class="btn" to="/login">前往登入</router-link><router-link v-else to="/login">返回登入</router-link></section></main></template>
<script setup>
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../api'
import { actionToken, withoutActionToken } from '../authLink'
const route=useRoute(), router=useRouter(), busy=ref(true), ok=ref(false), message=ref('')
onMounted(async()=>{
  const token = actionToken(route)
  await router.replace(withoutActionToken(route))
  if (!token) { message.value='驗證連結缺少 token，請從信件開啟完整連結'; busy.value=false; return }
  try{const r=await request('/auth/verify-email',{method:'POST',body:{token},withAuth:false});ok.value=true;message.value=r.message}catch(e){message.value=e.message||'驗證連結無效或已過期'}finally{busy.value=false}
})
</script>
<style scoped>.narrow{max-width:520px}h1{margin-top:0}</style>
