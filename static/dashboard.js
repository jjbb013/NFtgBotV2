function escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function updateTime() {
    document.getElementById('current-time').textContent = new Date().toLocaleString('zh-CN');
}
setInterval(updateTime, 1000);
updateTime();

async function apiGet(path) {
    const resp = await fetch(path);
    if (!resp.ok) {
        const text = await resp.text().catch(() => 'Unknown error');
        throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json();
}

async function apiPost(path, body) {
    const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!resp.ok) {
        const text = await resp.text().catch(() => 'Unknown error');
        throw new Error(`HTTP ${resp.status}: ${text}`);
    }
    return resp.json();
}

async function withErrorDisplay(elementId, fn) {
    const el = document.getElementById(elementId);
    try {
        await fn(el);
    } catch (err) {
        el.textContent = `加载失败: ${err.message}`;
    }
}

async function refreshSystemStatus() {
    await withErrorDisplay('system-status-content', async (el) => {
        const data = await apiGet('/api/system/status');
        el.innerHTML = `
            <p>运行版本: ${escapeHtml(data.active_version)}</p>
            <p>Git: ${escapeHtml(data.git.hash)} - ${escapeHtml(data.git.message)}</p>
            <p>提交时间: ${escapeHtml(data.git.time)}</p>
        `;
    });
}

async function refreshTelegramStatus() {
    await withErrorDisplay('telegram-status-content', async (el) => {
        const data = await apiGet('/api/telegram/status');
        let html = `
            <p>Session 文件: ${escapeHtml(data.session_path)}</p>
            <p>登录状态: ${data.authorized ? '有效' : '失效'}</p>
            <p>连接状态: ${data.connected ? '在线' : '离线'}</p>
            <p>监听频道: ${escapeHtml(data.channel_ids.join(', '))}</p>
        `;
        if (data.me) {
            html += `<p>当前用户: ${escapeHtml(data.me.first_name)} ${escapeHtml(data.me.last_name || '')} (@${escapeHtml(data.me.username || '')})</p>`;
        }
        el.innerHTML = html;
        document.getElementById('relogin-btn').style.display = data.authorized ? 'none' : 'inline-block';
    });
}

async function refreshOKXStatus() {
    await withErrorDisplay('okx-status-content', async (el) => {
        const data = await apiGet('/api/okx/status');
        let html = '';
        for (const acc of data.accounts) {
            html += `
                <div class="okx-card">
                    <h3>${escapeHtml(acc.name)}</h3>
                    <p>连接: ${acc.connected ? '正常' : '异常'}</p>
                    <p>USDT 余额: ${acc.balance !== null ? escapeHtml(acc.balance) : '获取失败'}</p>
                    <p>最近 7 天盈亏: ${acc.pnl !== null ? escapeHtml(acc.pnl) + ' USDT' : '获取失败'}</p>
                    <button class="load-orders-btn" data-account="${escapeHtml(acc.name)}">查看最近 20 条订单</button>
                    <div id="orders-${escapeHtml(acc.name)}"></div>
                </div>
            `;
        }
        el.innerHTML = html || '没有配置 OKX 账户';

        document.querySelectorAll('.load-orders-btn').forEach(btn => {
            btn.addEventListener('click', () => loadOrders(btn.dataset.account));
        });
    });
}

async function loadOrders(accountName) {
    const container = document.getElementById(`orders-${escapeHtml(accountName)}`);
    try {
        const data = await apiGet(`/api/okx/orders?account=${encodeURIComponent(accountName)}`);
        let html = '<table><tr><th>标的</th><th>方向</th><th>持仓方向</th><th>数量</th><th>均价</th><th>状态</th><th>时间</th></tr>';
        for (const o of data.orders) {
            html += `<tr><td>${escapeHtml(o.instId)}</td><td>${escapeHtml(o.side)}</td><td>${escapeHtml(o.posSide)}</td><td>${escapeHtml(o.sz)}</td><td>${escapeHtml(o.avgPx)}</td><td>${escapeHtml(o.state)}</td><td>${escapeHtml(o.cTime ? new Date(parseInt(o.cTime)).toLocaleString('zh-CN') : '-')}</td></tr>`;
        }
        html += '</table>';
        container.innerHTML = html;
    } catch (err) {
        container.textContent = `加载订单失败: ${err.message}`;
    }
}

async function refreshLogs() {
    await withErrorDisplay('logs-content', async (el) => {
        const data = await apiGet('/api/logs');
        el.textContent = data.lines.join('\n');
    });
}

async function refreshAll() {
    await Promise.all([
        refreshSystemStatus(),
        refreshTelegramStatus(),
        refreshOKXStatus(),
        refreshLogs(),
    ]);
}

let loginState = {};

function showLoginWizard() {
    document.getElementById('login-wizard').style.display = 'block';
}

async function startLogin() {
    const phone = document.getElementById('phone').value;
    try {
        const result = await apiPost('/api/telegram/login/start', { phone });
        loginState = { phone, phone_code_hash: result.phone_code_hash };
        document.getElementById('login-step-1').style.display = 'none';
        document.getElementById('login-step-2').style.display = 'block';
        document.getElementById('login-result').textContent = result.message || '';
    } catch (err) {
        document.getElementById('login-result').textContent = `发送验证码失败: ${err.message}`;
    }
}

async function verifyCode() {
    const code = document.getElementById('code').value;
    try {
        const result = await apiPost('/api/telegram/login/verify', {
            phone: loginState.phone,
            code,
            phone_code_hash: loginState.phone_code_hash,
        });
        if (result.need_password) {
            document.getElementById('login-step-2').style.display = 'none';
            document.getElementById('login-step-3').style.display = 'block';
        } else {
            finishLogin(result);
        }
    } catch (err) {
        document.getElementById('login-result').textContent = `验证码验证失败: ${err.message}`;
    }
}

async function verifyPassword() {
    const password = document.getElementById('password').value;
    try {
        const result = await apiPost('/api/telegram/login/password', { password });
        finishLogin(result);
    } catch (err) {
        document.getElementById('login-result').textContent = `密码验证失败: ${err.message}`;
    }
}

function finishLogin(result) {
    const el = document.getElementById('login-result');
    if (result.success) {
        el.textContent = '登录成功';
        setTimeout(() => location.reload(), 2000);
    } else {
        el.textContent = `登录失败: ${escapeHtml(result.error || '未知错误')}`;
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('refresh-all-btn').addEventListener('click', refreshAll);
    document.getElementById('relogin-btn').addEventListener('click', showLoginWizard);
    document.getElementById('start-login-btn').addEventListener('click', startLogin);
    document.getElementById('verify-code-btn').addEventListener('click', verifyCode);
    document.getElementById('verify-password-btn').addEventListener('click', verifyPassword);
    document.getElementById('refresh-logs-btn').addEventListener('click', refreshLogs);
    refreshAll();
});
