<template><main class="page narrow"><form class="panel" @submit.prevent="submit"><h1>忘記密碼</h1><p class="muted">輸入學校信箱後，若帳號存在，系統會寄送一小時內有效的重設連結。</p><div class="field"><label class="required" for="email">學校信箱</label><input id="email" v-model.trim="email" type="email" required /></div><p v-if="message" class="alert alert-info">{{ message }}</p><p v-if="error" class="alert alert-error">{{ error }}</p><button class="btn btn-large" :disabled="busy">{{ busy?'送出中…':'寄送重設連結' }}</button><p class="note"><router-link to="/login">返回登入</router-link></p></form></main></template>
<script setup>
import {ref} from 'vue';import{request}from'../api'
const email=ref(''),message=ref(''),error=ref(''),busy=ref(false)
async function submit(){busy.value=true;error.value='';message.value='';try{const r=await request('/auth/forgot-password',{method:'POST',body:{email:email.value},withAuth:false});message.value=r.message}catch(e){error.value=e.message}finally{busy.value=false}}
</script>
<style scoped>.narrow{max-width:480px}h1{margin-top:0}.note{text-align:center}</style>
