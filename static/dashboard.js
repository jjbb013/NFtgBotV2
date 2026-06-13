function updateTime() {
    document.getElementById('current-time').textContent = new Date().toLocaleString('zh-CN');
}
setInterval(updateTime, 1000);
updateTime();

async function refreshAll() {
    await Promise.all([
        refreshSystemStatus(),
        refreshTelegramStatus(),
        refreshOKXStatus(),
        refreshLogs(),
    ]);
}

async function apiGet(path) {
    const resp = await fetch(path);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
}

async function apiPost(path, body) {
    const resp = await fetch(path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    return resp.json();
}

async function refreshSystemStatus() {
    const data = await apiGet('/api/system/status');
    document.getElementById('system-status-content').innerHTML = `
        <p>运行版本: ${data.active_version}</p>
        <p>Git: ${data.git.hash} - ${data.git.message}</p>
        <p>提交时间: ${data.git.time}</p>
    `;
}

async function refreshTelegramStatus() {
    const data = await apiGet('/api/telegram/status');
    let html = `
        <p>Session 文件: ${data.session_path}</p>
        <p>登录状态: ${data.authorized ? '有效' : '失效'}</p>
        <p>连接状态: ${data.connected ? '在线' : '离线'}</p>
        <p>监听频道: ${data.channel_ids.join(', ')}</p>
    `;
    if (data.me) {
        html += `<p>当前用户: ${data.me.first_name} ${data.me.last_name || ''} (@${data.me.username || ''})</p>`;
    }
    document.getElementById('telegram-status-content').innerHTML = html;
    document.getElementById('relogin-btn').style.display = data.authorized ? 'none' : 'inline-block';
}

async function refreshOKXStatus() {
    const data = await apiGet('/api/okx/status');
    let html = '';
    for (const acc of data.accounts) {
        html += `
            <div class="okx-card">
                <h3>${acc.name}</h3>
                <p>连接: ${acc.connected ? '正常' : '异常'}</p>
                <p>USDT 余额: ${acc.balance !== null ? acc.balance : '获取失败'}</p>
                <p>最近 7 天盈亏: ${acc.pnl !== null ? acc.pnl + ' USDT' : '获取失败'}</p>
                <button onclick="loadOrders('${acc.name}')">查看最近 20 条订单</button>
                <div id="orders-${acc.name}"></div>
            </div>
        `;
    }
    document.getElementById('okx-status-content').innerHTML = html || '没有配置 OKX 账户';
}

async function loadOrders(accountName) {
    const data = await apiGet(`/api/okx/orders?account=${encodeURIComponent(accountName)}`);
    let html = '<table border="1" cellpadding="5"><tr><th>标的</th><th>方向</th><th>持仓方向</th><th>数量</th><th>均价</th><th>状态</th><th>时间</th></tr>';
    for (const o of data.orders) {
        html += `<tr><td>${o.instId}</td><td>${o.side}</td><td>${o.posSide}</td><td>${o.sz}</td><td>${o.avgPx}</td><td>${o.state}</td><td>${new Date(parseInt(o.cTime)).toLocaleString('zh-CN')}</td></tr>`;
    }
    html += '</table>';
    document.getElementById(`orders-${accountName}`).innerHTML = html;
}

async function refreshLogs() {
    const data = await apiGet('/api/logs');
    document.getElementById('logs-content').textContent = data.lines.join('\n');
}

let loginState = {};

function showLoginWizard() {
    document.getElementById('login-wizard').style.display = 'block';
}

async function startLogin() {
    const phone = document.getElementById('phone').value;
    const result = await apiPost('/api/telegram/login/start', { phone });
    loginState = { phone, phone_code_hash: result.phone_code_hash };
    document.getElementById('login-step-1').style.display = 'none';
    document.getElementById('login-step-2').style.display = 'block';
    document.getElementById('login-result').textContent = result.message || '';
}

async function verifyCode() {
    const code = document.getElementById('code').value;
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
}

async function verifyPassword() {
    const password = document.getElementById('password').value;
    const result = await apiPost('/api/telegram/login/password', { password });
    finishLogin(result);
}

function finishLogin(result) {
    document.getElementById('login-result').textContent = result.success ? '登录成功' : `登录失败: ${result.error}`;
    if (result.success) {
        setTimeout(() => location.reload(), 2000);
    }
}

refreshAll();
