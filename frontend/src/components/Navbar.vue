<template>
    <nav class="navbar">
        <div class="nav-brand">海大活動報名系統</div>
        <div class="nav-search">
            <input type="text" placeholder="搜尋活動關鍵字..." class="search-input" />
            <button class="search-btn">搜尋</button>
        </div>
        <div class="nav-actions">
            <button class="btn-outline">登入</button>
            <button class="btn-primary">註冊</button>
        </div>
    </nav>
</template>

<style scoped>
    .navbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 24px;
        background-color: #fff;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        position: sticky;
        top: 0;
        z-index: 100;
    }
    .nav-brand {
        font-size: 1.25rem;
        font-weight: bold;
        color: #004d99;
    }
    .nav-search {
        display: flex;
        gap: 8px;
        flex: 1;
        max-width: 400px;
    }
    .search-input {
        flex: 1;
        padding: 8px 12px;
        border: 1px solid #ccc;
        border-radius: 4px;
    }
    .btn-primary, .btn-outline, .search-btn {
        padding: 8px 16px;
        border-radius: 4px;
        cursor: pointer;
        font-weight: bold;
    }
    .btn-primary, .search-btn {
        background-color: #004d99;
        color: white;
        border: none;
    }
    .btn-outline {
        background-color: transparent;
        color: #004d99;
        border: 1px solid #004d99;
        margin-right: 8px;
    }
</style>