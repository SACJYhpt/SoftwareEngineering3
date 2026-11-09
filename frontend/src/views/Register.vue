<template>
  <main class="page narrow">
    <form class="panel" @submit.prevent="submit">
      <h1>建立帳號</h1>
      <p class="muted">僅接受學校信箱（@ntou.edu.tw 或 @mail.ntou.edu.tw）。註冊後須先完成信箱驗證才能登入。</p>
      <div class="field"><label class="required" for="email">學校信箱</label><input id="email" v-model.trim="form.email" type="email" autocomplete="email" required /></div>
      <div class="field"><label class="required" for="name">姓名</label><input id="name" v-model.trim="form.name" maxlength="100" required /></div>
      <div class="field"><label class="required" for="identity">身分別</label>
        <select id="identity" v-model="form.identity" required>
          <option value="student">學生</option><option value="teacher">教師</option><option value="staff">行政人員</option>
        </select>
        <span class="hint">身分別註冊後不可自行修改，請務必確認選擇正確。</span>
      </div>
      <div class="field"><label class="required" for="department">系所</label>
        <select id="department" v-model.number="form.department_id" required>
          <option disabled value="">請選擇系所</option><option v-for="unit in units" :key="unit.id" :value="unit.id">{{ unit.name }}</option>
        </select>
      </div>
      <div v-if="form.identity === 'student'" class="field"><label class="required" for="grade">年級</label>
        <select id="grade" v-model.number="form.grade" required>
          <option disabled value="">請選擇年級</option><option v-for="n in 8" :key="n" :value="n">{{ n > 4 ? '研究所 ' + (n - 4) + ' 年級' : n + ' 年級' }}</option>
        </select>
      </div>
      <div class="field"><label class="required" for="password">密碼</label><input id="password" v-model="form.password" type="password" minlength="8" autocomplete="new-password" required />
        <span class="hint">至少 8 碼，且同時包含英文字母與數字。</span>
      </div>
      <div class="field"><label class="required" for="confirm">確認密碼</label><input id="confirm" v-model="confirm" type="password" autocomplete="new-password" required /></div>
      <p v-if="error" class="alert alert-error">{{ error }}</p><p v-if="success" class="alert alert-ok">{{ success }}</p>
      <button class="btn btn-large" :disabled="busy">{{ busy ? '註冊中…' : '註冊帳號' }}</button>
      <p class="muted note">已經有帳號？<router-link to="/login">前往登入</router-link></p>
    </form>
  </main>
</template>
<script setup>
import { onMounted, reactive, ref } from 'vue'
import { request } from '../api'
const units = ref([]), busy = ref(false), error = ref(''), success = ref(''), confirm = ref('')
const form = reactive({ email: '', name: '', identity: 'student', department_id: '', grade: '', password: '' })
onMounted(async () => { try { units.value = await request('/units', { withAuth: false }) } catch (e) { error.value = '無法載入系所清單：' + e.message } })
async function submit() {
  error.value = ''; success.value = ''
  if (form.password.length < 8 || !/[A-Za-z]/.test(form.password) || !/[0-9]/.test(form.password)) { error.value = '密碼至少 8 碼，且須同時包含英文字母與數字'; return }
  if (form.password !== confirm.value) { error.value = '兩次輸入的密碼不一致'; return }
  busy.value = true
  try {
    const payload = { ...form, grade: form.identity === 'student' ? Number(form.grade) : null, department_id: Number(form.department_id) }
    await request('/auth/register', { method: 'POST', body: payload, withAuth: false })
    success.value = '註冊成功！請至學校信箱收取驗證信，完成驗證後才能登入。'
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
</script>
<style scoped>.narrow{max-width:520px}h1{margin-top:0}.note{text-align:center;margin-bottom:0}</style>
