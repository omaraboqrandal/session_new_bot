/* ═══════════════════════════════════════════════════════════════
   Session Manager Panel — Client-side JavaScript
   ═══════════════════════════════════════════════════════════════ */

// ── Sidebar Toggle (mobile) ────────────────────────────────────

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('open');
}

// Close sidebar on outside click (mobile)
document.addEventListener('click', function(e) {
    const sidebar = document.getElementById('sidebar');
    const toggle = document.querySelector('.menu-toggle');
    if (sidebar && sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) && !toggle.contains(e.target)) {
        sidebar.classList.remove('open');
    }
});

// ── Toast Notifications ────────────────────────────────────────

function showToast(message, type = 'success') {
    const existing = document.querySelector('.toast');
    if (existing) existing.remove();

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.opacity = '0';
        toast.style.transform = 'translateY(20px)';
        toast.style.transition = 'all 0.3s';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// ── API Helper ─────────────────────────────────────────────────

async function api(url, options = {}) {
    try {
        const res = await fetch(url, {
            headers: { 'Content-Type': 'application/json', ...options.headers },
            ...options,
        });
        const data = await res.json();
        if (!res.ok) {
            throw new Error(data.detail || data.error || 'Request failed');
        }
        return data;
    } catch (e) {
        if (e.message === 'Request failed' || e instanceof TypeError) {
            showToast('Network error. Please try again.', 'error');
        } else {
            showToast(e.message, 'error');
        }
        throw e;
    }
}

// ── Sections (navigate without page reload for API sections) ───

function showSection(section) {
    // Just scroll to the section on the dashboard
    const el = document.getElementById(section + 'Section');
    if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
        el.style.borderColor = '#38bdf8';
        setTimeout(() => { el.style.borderColor = ''; }, 2000);
    }
}

// ── Sessions ───────────────────────────────────────────────────

async function viewCountrySessions(folder) {
    const modal = document.getElementById('modalOverlay');
    const body = document.getElementById('modalBody');
    const title = document.getElementById('modalTitle');

    title.textContent = 'Loading...';
    body.innerHTML = '<p style="text-align:center;color:#94a3b8;">Loading sessions...</p>';
    modal.classList.add('active');

    try {
        const data = await api('/api/sessions');
        const country = data[folder];
        if (!country) {
            body.innerHTML = '<p>Country not found</p>';
            return;
        }

        title.textContent = `${country.flag} ${country.name} (${country.phones.length})`;

        let html = '<table class="table"><thead><tr><th>Phone</th><th>Spam</th><th>Contact</th><th>Actions</th></tr></thead><tbody>';
        for (const p of country.phones) {
            const spamClass = {
                'FREE': 'badge-green', 'SPAM': 'badge-yellow',
                'BANNED': 'badge-red', 'Unknown': 'badge-gray'
            }[p.spam_status] || 'badge-gray';

            const contactClass = {
                'NoLimit': 'badge-green', 'Limited': 'badge-yellow', 'Unknown': 'badge-gray'
            }[p.contact_status] || 'badge-gray';

            html += `<tr>
                <td><code>+${p.phone}</code></td>
                <td><span class="badge ${spamClass}">${p.spam_status}</span></td>
                <td><span class="badge ${contactClass}">${p.contact_status}</span></td>
                <td>
                    <button class="btn btn-xs btn-outline" onclick="sessionAction('otp', '${p.phone}')">OTP</button>
                    <button class="btn btn-xs btn-danger" onclick="sessionAction('logout', '${p.phone}')">Logout</button>
                    <button class="btn btn-xs btn-danger" onclick="sessionAction('delete', '${p.phone}')">Delete</button>
                </td>
            </tr>`;
        }
        html += '</tbody></table>';
        body.innerHTML = html;

    } catch (e) {
        body.innerHTML = `<p style="color:#ef4444;">Error loading sessions</p>`;
    }
}

async function sessionAction(action, phone) {
    if (action === 'logout') {
        if (!confirm(`Log out +${phone}? This will terminate the Telegram session.`)) return;
        try {
            await api(`/api/sessions/${phone}/logout`, { method: 'POST' });
            showToast(`+${phone} logged out successfully`);
            closeModal();
            setTimeout(() => location.reload(), 1000);
        } catch (e) { /* toast shown by api() */ }
    }
    else if (action === 'delete') {
        if (!confirm(`Delete +${phone}? This cannot be undone.`)) return;
        try {
            await api(`/api/sessions/${phone}`, { method: 'DELETE' });
            showToast(`+${phone} deleted`);
            closeModal();
            setTimeout(() => location.reload(), 1000);
        } catch (e) { /* toast shown by api() */ }
    }
    else if (action === 'otp') {
        showToast('Fetching OTP...', 'success');
        try {
            const data = await api(`/api/sessions/${phone}/otp`);
            if (data.found) {
                // Strip HTML tags for toast
                const text = data.message.replace(/<[^>]*>/g, '');
                showToast(`OTP: ${text}`);
            } else {
                showToast(data.message || 'No code found', 'error');
            }
        } catch (e) { /* toast shown by api() */ }
    }
}

async function exportAllSessions() {
    showToast('Preparing export...');
    try {
        const res = await fetch('/api/sessions/export/all');
        if (!res.ok) {
            const data = await res.json();
            throw new Error(data.detail || 'Export failed');
        }
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'sessions_export.zip';
        a.click();
        URL.revokeObjectURL(url);
        showToast('Export downloaded!');
    } catch (e) {
        showToast(e.message || 'Export failed', 'error');
    }
}

// ── Admins ─────────────────────────────────────────────────────

function showAddAdmin() {
    document.getElementById('addAdminModal').classList.add('active');
}

function closeAddAdmin() {
    document.getElementById('addAdminModal').classList.remove('active');
}

async function addAdmin() {
    const userId = document.getElementById('adminUserId').value;
    const role = document.getElementById('adminRole').value;

    if (!userId) {
        showToast('Please enter a User ID', 'error');
        return;
    }

    try {
        await api('/api/admins', {
            method: 'POST',
            body: JSON.stringify({ user_id: parseInt(userId), role: role }),
        });
        showToast(`Admin ${userId} added`);
        closeAddAdmin();
        setTimeout(() => location.reload(), 500);
    } catch (e) { /* toast shown by api() */ }
}

async function removeAdmin(userId) {
    if (!confirm(`Remove admin ${userId}?`)) return;
    try {
        await api(`/api/admins/${userId}`, { method: 'DELETE' });
        showToast(`Admin ${userId} removed`);
        setTimeout(() => location.reload(), 500);
    } catch (e) { /* toast shown by api() */ }
}

// ── Settings ───────────────────────────────────────────────────

async function refreshSettings() {
    const container = document.getElementById('settingsContent');
    container.innerHTML = '<p style="text-align:center;color:#94a3b8;">Loading...</p>';

    try {
        const data = await api('/api/settings');
        let html = '<div class="scheduler-grid">';

        // Proxy
        html += `<div class="scheduler-item">
            <div class="scheduler-info">
                <span class="scheduler-name">Proxy</span>
                <span class="scheduler-desc">${data.proxy.enabled ? 'Enabled' : 'Disabled'} | ${data.proxy.type} | ${data.proxy.host || 'Not set'}:${data.proxy.port || '-'}</span>
            </div>
            <span class="badge ${data.proxy.enabled ? 'badge-green' : 'badge-gray'}">${data.proxy.enabled ? 'ON' : 'OFF'}</span>
        </div>`;

        // API
        html += `<div class="scheduler-item">
            <div class="scheduler-info">
                <span class="scheduler-name">API Credentials</span>
                <span class="scheduler-desc">ID: ${data.api.api_id} | Hash: ${data.api.api_hash}</span>
            </div>
        </div>`;

        // Profile
        const profile = data.profile;
        html += `<div class="scheduler-item">
            <div class="scheduler-info">
                <span class="scheduler-name">Profile Auto-fill</span>
                <span class="scheduler-desc">
                    Username: ${profile.auto_username ? 'ON' : 'OFF'} |
                    Name: ${profile.auto_name ? 'ON' : 'OFF'} |
                    Photo: ${profile.auto_photo ? 'ON' : 'OFF'} |
                    Bio: ${profile.auto_bio ? 'ON' : 'OFF'}
                </span>
            </div>
        </div>`;

        html += '</div>';
        container.innerHTML = html;

    } catch (e) {
        container.innerHTML = '<p style="color:#ef4444;">Failed to load settings</p>';
    }
}

// ── Scheduler ──────────────────────────────────────────────────

async function toggleScheduler(feature) {
    try {
        const data = await api(`/api/scheduler/toggle/${feature}`, { method: 'POST' });
        showToast(`${feature.replace('_', ' ')} ${data.enabled ? 'enabled' : 'disabled'}`);
    } catch (e) {
        // Revert checkbox
        const cbMap = {
            'auto_check': 'toggleAutoCheck',
            'daily_report': 'toggleDailyReport',
            'auto_backup': 'toggleAutoBackup',
        };
        const cb = document.getElementById(cbMap[feature]);
        if (cb) cb.checked = !cb.checked;
    }
}

// ── Modal ──────────────────────────────────────────────────────

function closeModal() {
    document.getElementById('modalOverlay').classList.remove('active');
}

// Close on Escape key
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        closeModal();
        closeAddAdmin();
    }
});
