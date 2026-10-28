document.addEventListener('DOMContentLoaded', () => {
  // ========== GOOGLE SIGN-IN ==========
  const loginOverlay = document.getElementById('loginOverlay');
  const appContainer = document.getElementById('appContainer');
  const userBadge = document.getElementById('userBadge');
  const userAvatar = document.getElementById('userAvatar');
  const userNameEl = document.getElementById('userName');
  const btnSignOut = document.getElementById('btnSignOut');

  let currentUser = null;

  // Check for existing session
  const savedUser = localStorage.getItem('calculator_user');
  if (savedUser) {
    try {
      currentUser = JSON.parse(savedUser);
      showApp(currentUser);
      // Sync user profile to backend & Firestore
      fetch('/api/auth/sync', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(currentUser)
      }).catch(err => console.warn('User sync skipped:', err));
    } catch (e) {
      localStorage.removeItem('calculator_user');
    }
  }

  // Initialize Google Sign-In
  function initGoogleSignIn() {
    if (typeof google === 'undefined' || !google.accounts) {
      // Google library not loaded yet, retry
      setTimeout(initGoogleSignIn, 200);
      return;
    }
    google.accounts.id.initialize({
      client_id: window.GOOGLE_CLIENT_ID || '570480688616-1kfggobt8nu318kktd8ao689u6pmln6s.apps.googleusercontent.com',
      callback: handleGoogleSignIn,
      auto_select: false,
    });
    google.accounts.id.renderButton(
      document.getElementById('googleSignInButton'),
      {
        theme: 'filled_blue',
        size: 'large',
        shape: 'pill',
        text: 'signin_with',
        width: 280,
      }
    );
    // Show one-tap prompt if not already signed in
    if (!currentUser) {
      google.accounts.id.prompt();
    }
  }

  async function handleGoogleSignIn(response) {
    try {
      const res = await fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential }),
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Authentication failed');
      }

      const data = await res.json();
      currentUser = data.user;
      localStorage.setItem('calculator_user', JSON.stringify(currentUser));
      showApp(currentUser);
    } catch (err) {
      console.error('Sign-in error:', err);
      alert('Sign-in failed. Please try again.');
    }
  }

  function showApp(user) {
    loginOverlay.style.display = 'none';
    appContainer.style.display = 'flex';
    userBadge.style.display = 'flex';
    userAvatar.src = user.picture || '';
    userNameEl.textContent = user.name || user.email;
  }

  function signOut() {
    currentUser = null;
    localStorage.removeItem('calculator_user');
    if (typeof google !== 'undefined' && google.accounts) {
      google.accounts.id.disableAutoSelect();
    }
    loginOverlay.style.display = 'flex';
    appContainer.style.display = 'none';
    userBadge.style.display = 'none';
  }

  btnSignOut.addEventListener('click', signOut);

  // ========== IN-APP ADMIN MODAL LOGIC ==========
  const btnOpenAdmin = document.getElementById('btnOpenAdmin');
  const btnCloseAdmin = document.getElementById('btnCloseAdmin');
  const btnAdminRefresh = document.getElementById('btnAdminRefresh');
  const adminModalOverlay = document.getElementById('adminModalOverlay');
  const adminModalBody = document.getElementById('adminModalBody');

  if (btnOpenAdmin) {
    btnOpenAdmin.addEventListener('click', () => {
      adminModalOverlay.style.display = 'flex';
      loadAdminSummary();
    });
  }

  if (btnCloseAdmin) {
    btnCloseAdmin.addEventListener('click', () => {
      adminModalOverlay.style.display = 'none';
    });
  }

  if (btnAdminRefresh) {
    btnAdminRefresh.addEventListener('click', loadAdminSummary);
  }

  // Click outside card to close
  if (adminModalOverlay) {
    adminModalOverlay.addEventListener('click', (e) => {
      if (e.target === adminModalOverlay) {
        adminModalOverlay.style.display = 'none';
      }
    });
  }

  async function loadAdminSummary() {
    adminModalBody.innerHTML = '<div class="admin-loading">Loading users & calculations from Firestore...</div>';
    try {
      const res = await fetch('/api/admin/summary');
      if (!res.ok) throw new Error('Failed to load admin summary');
      const data = await res.json();

      const users = data.users || [];
      const m = data.metrics || { lifetime: {}, last_7_days: {} };
      const lt = m.lifetime || { total_users: 0, total_sessions: 0, total_calculations: 0 };
      const w7 = m.last_7_days || { active_users: 0, sessions: 0, calculations: 0 };

      let metricsHtml = `
        <div class="modal-metrics-wrap">
          <div class="modal-metrics-title">🌐 Lifetime Summary</div>
          <div class="modal-metrics-grid">
            <div class="modal-metric-card">
              <span class="modal-metric-label">Lifetime Users</span>
              <span class="modal-metric-num">${lt.total_users || 0}</span>
            </div>
            <div class="modal-metric-card">
              <span class="modal-metric-label">Total Sessions</span>
              <span class="modal-metric-num">${lt.total_sessions || 0}</span>
            </div>
            <div class="modal-metric-card">
              <span class="modal-metric-label">Total Calculations</span>
              <span class="modal-metric-num">${lt.total_calculations || 0}</span>
            </div>
          </div>

          <div class="modal-metrics-title" style="color:#38bdf8;margin-top:0.9rem;">⚡ Last 7 Days Activity</div>
          <div class="modal-metrics-grid">
            <div class="modal-metric-card recent">
              <span class="modal-metric-label">Active Users (7d)</span>
              <span class="modal-metric-num">${w7.active_users || 0}</span>
            </div>
            <div class="modal-metric-card recent">
              <span class="modal-metric-label">Sessions (7d)</span>
              <span class="modal-metric-num">${w7.sessions || 0}</span>
            </div>
            <div class="modal-metric-card recent">
              <span class="modal-metric-label">Calculations (7d)</span>
              <span class="modal-metric-num">${w7.calculations || 0}</span>
            </div>
          </div>
        </div>
        <div class="modal-metrics-title" style="margin-top:1.25rem;">📋 Registered Users & Logs</div>
      `;

      if (!users || users.length === 0) {
        adminModalBody.innerHTML = metricsHtml + '<div class="admin-loading">No users have signed in yet.</div>';
        return;
      }

      let cardsHtml = '';
      users.forEach(u => {
        const avatar = u.picture
          ? `<img class="admin-user-avatar" src="${escapeHtml(u.picture)}" alt="avatar">`
          : '<div class="admin-user-avatar" style="display:flex;align-items:center;justify-content:center;background:#334155;color:#94a3b8;">👤</div>';

        const calcs = u.calculations || [];
        const calcCount = calcs.length || u.calculation_count || 0;

        let calcsListHtml = '';
        if (calcs.length > 0) {
          const items = calcs.map(c => `
            <li class="admin-calc-item">
              <div>
                <span class="admin-calc-expr">${escapeHtml(c.expression)}</span>
                <span class="admin-calc-res">= ${escapeHtml(c.result)}</span>
              </div>
              <span class="admin-calc-time">${escapeHtml(c.timestamp || '')}</span>
            </li>
          `).join('');

          calcsListHtml = `
            <div class="admin-calcs-section">
              <details class="admin-calcs-toggle" open>
                <summary>▸ Calculations History (${calcCount})</summary>
                <ul class="admin-calcs-list">
                  ${items}
                </ul>
              </details>
            </div>
          `;
        } else {
          calcsListHtml = `
            <div class="admin-calcs-section" style="color:#64748b;font-size:0.8rem;font-style:italic;">
              No calculations recorded yet.
            </div>
          `;
        }

        cardsHtml += `
          <div class="admin-user-card">
            <div class="admin-user-header">
              <div class="admin-user-meta">
                ${avatar}
                <div class="admin-user-title">
                  <span class="admin-user-name">${escapeHtml(u.name || 'Anonymous')}</span>
                  <span class="admin-user-email">${escapeHtml(u.email || '')}</span>
                </div>
              </div>
              <div class="admin-stats-row">
                <span class="admin-stat-pill">Logins: <strong>${u.login_count || 1}</strong></span>
                <span class="admin-stat-pill">Calculations: <strong>${calcCount}</strong></span>
              </div>
            </div>
            ${calcsListHtml}
          </div>
        `;
      });

      adminModalBody.innerHTML = metricsHtml + cardsHtml;
    } catch (err) {
      console.error('Failed to load admin summary:', err);
      adminModalBody.innerHTML = `<div class="admin-loading" style="color:#ef4444;">Failed to load activity: ${escapeHtml(err.message)}</div>`;
    }
  }

  // Fetch the client ID from the server, then init
  fetch('/api/auth/client-id')
    .then(r => r.json())
    .then(data => {
      window.GOOGLE_CLIENT_ID = data.client_id;
      initGoogleSignIn();
    })
    .catch(() => {
      // Fallback: try initializing anyway
      initGoogleSignIn();
    });

  // ========== CALCULATOR LOGIC (unchanged) ==========
  const mainDisplay = document.getElementById('mainDisplay');
  const expressionDisplay = document.getElementById('expressionDisplay');
  const historyDrawer = document.getElementById('historyDrawer');
  const historyList = document.getElementById('historyList');
  const btnHistory = document.getElementById('btnHistory');
  const btnCloseHistory = document.getElementById('btnCloseHistory');
  const btnClearHistory = document.getElementById('btnClearHistory');
  const btnClear = document.getElementById('btnClear');
  const btnBackspace = document.getElementById('btnBackspace');
  const keys = document.querySelectorAll('.key');

  let currentExpression = '';
  let evaluated = false;

  // Format expression for LCD display
  function formatForDisplay(expr) {
    if (!expr) return '0';
    return expr
      .replace(/\*/g, ' × ')
      .replace(/\//g, ' ÷ ')
      .replace(/\+/g, ' + ')
      .replace(/(?<=\d|\))\-(?=\d|\()/g, ' − ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  // Persistent Client-Side History (survives serverless container scale-to-zero)
  const STORAGE_KEY = 'cloud_calculator_history';

  function getLocalHistory() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : [];
    } catch (e) {
      console.warn('Could not read from localStorage', e);
      return [];
    }
  }

  function saveLocalHistory(history) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, 100)));
    } catch (e) {
      console.warn('Could not write to localStorage', e);
    }
  }

  function addHistoryItem(item) {
    const list = getLocalHistory();
    list.unshift(item);
    saveLocalHistory(list);
  }

  // Update Display
  function updateDisplay() {
    if (currentExpression === '') {
      mainDisplay.textContent = '0';
    } else {
      mainDisplay.textContent = formatForDisplay(currentExpression);
    }
  }

  // Append Character
  function appendValue(val) {
    if (evaluated) {
      if (['+', '-', '*', '/', '%', '**'].includes(val)) {
        // Continue operating on previous result
        evaluated = false;
      } else {
        // Start fresh
        currentExpression = '';
        evaluated = false;
      }
    }

    if (val === 'sqrt') {
      currentExpression = `sqrt(${currentExpression || ''}`;
      updateDisplay();
      return;
    }

    if (val === '()') {
      const openCount = (currentExpression.match(/\(/g) || []).length;
      const closeCount = (currentExpression.match(/\)/g) || []).length;
      if (openCount > closeCount && !['(', '+', '-', '*', '/'].includes(currentExpression.slice(-1))) {
        currentExpression += ')';
      } else {
        currentExpression += '(';
      }
      updateDisplay();
      return;
    }

    // Prevent consecutive invalid operators
    const lastChar = currentExpression.slice(-1);
    const operators = ['+', '-', '*', '/', '%'];
    if (operators.includes(val) && operators.includes(lastChar)) {
      currentExpression = currentExpression.slice(0, -1) + val;
      updateDisplay();
      return;
    }

    currentExpression += val;
    updateDisplay();
  }

  // Clear All
  function clearAll() {
    currentExpression = '';
    expressionDisplay.textContent = '';
    evaluated = false;
    updateDisplay();
  }

  // Backspace
  function backspace() {
    if (evaluated) {
      clearAll();
      return;
    }
    if (currentExpression.endsWith('sqrt(')) {
      currentExpression = currentExpression.slice(0, -5);
    } else {
      currentExpression = currentExpression.slice(0, -1);
    }
    updateDisplay();
  }

  // Perform Calculation (calls Python FastAPI backend)
  async function computeResult() {
    if (!currentExpression.trim()) return;

    // Auto close unmatched parentheses
    let expr = currentExpression;
    const openCount = (expr.match(/\(/g) || []).length;
    const closeCount = (expr.match(/\)/g) || []).length;
    if (openCount > closeCount) {
      expr += ')'.repeat(openCount - closeCount);
    }

    expressionDisplay.textContent = `${formatForDisplay(expr)} =`;

    try {
      const response = await fetch('/api/calculate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          expression: expr,
          email: currentUser ? currentUser.email : null
        })
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Calculation error');
      }

      const data = await response.json();
      currentExpression = data.display_result;
      evaluated = true;
      updateDisplay();

      // Persist to client-side localStorage
      addHistoryItem({
        id: Date.now(),
        expression: expr,
        result: data.display_result,
        timestamp: data.timestamp || new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
      });
    } catch (err) {
      mainDisplay.textContent = 'Error';
      console.error('Calculation Error:', err);
      setTimeout(() => {
        updateDisplay();
      }, 1500);
    }
  }

  // History Drawer Handling
  async function loadHistory() {
    try {
      let data = getLocalHistory();
      if (currentUser && currentUser.email) {
        try {
          const res = await fetch(`/api/history?email=${encodeURIComponent(currentUser.email)}`);
          if (res.ok) {
            const serverHistory = await res.json();
            if (serverHistory && serverHistory.length > 0) {
              data = serverHistory;
              saveLocalHistory(data);
            }
          }
        } catch (e) {
          console.warn('Could not fetch server history, falling back to local', e);
        }
      }

      if (!data || data.length === 0) {
        historyList.innerHTML = '<div class="empty-history">No calculations yet</div>';
        return;
      }

      historyList.innerHTML = '';
      data.forEach(item => {
        const itemEl = document.createElement('div');
        itemEl.className = 'history-item';
        itemEl.innerHTML = `
          <div class="history-item-content">
            <div class="history-expr">${escapeHtml(item.expression)}</div>
            <div class="history-result">${escapeHtml(item.result)}</div>
          </div>
          <button class="delete-item-btn" title="Remove calculation" aria-label="Delete calculation">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M3 6h18"></path>
              <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
              <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
            </svg>
          </button>
        `;

        const contentEl = itemEl.querySelector('.history-item-content');
        contentEl.addEventListener('click', () => {
          currentExpression = item.result;
          evaluated = false;
          updateDisplay();
          historyDrawer.classList.remove('open');
        });

        const deleteBtn = itemEl.querySelector('.delete-item-btn');
        deleteBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          deleteHistoryItem(item.id, itemEl);
        });

        historyList.appendChild(itemEl);
      });
    } catch (err) {
      console.error('Failed to load history', err);
    }
  }

  function deleteHistoryItem(id, itemEl) {
    try {
      let list = getLocalHistory();
      list = list.filter(item => item.id !== id);
      saveLocalHistory(list);

      itemEl.classList.add('removing');
      setTimeout(() => {
        itemEl.remove();
        if (historyList.querySelectorAll('.history-item').length === 0) {
          historyList.innerHTML = '<div class="empty-history">No calculations yet</div>';
        }
      }, 180);
    } catch (err) {
      console.error('Failed to delete history item', err);
    }
  }

  function clearHistory() {
    try {
      saveLocalHistory([]);
      historyList.innerHTML = '<div class="empty-history">History cleared</div>';
    } catch (err) {
      console.error('Failed to clear history', err);
    }
  }

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Button Click Listeners
  keys.forEach(key => {
    key.addEventListener('click', () => {
      const k = key.dataset.key;
      triggerVisualFeedback(key);
      if (k === '=') {
        computeResult();
      } else {
        appendValue(k);
      }
    });
  });

  btnClear.addEventListener('click', () => {
    triggerVisualFeedback(btnClear);
    clearAll();
  });

  btnBackspace.addEventListener('click', () => {
    triggerVisualFeedback(btnBackspace);
    backspace();
  });

  btnHistory.addEventListener('click', () => {
    loadHistory();
    historyDrawer.classList.add('open');
  });

  btnCloseHistory.addEventListener('click', () => {
    historyDrawer.classList.remove('open');
  });

  btnClearHistory.addEventListener('click', clearHistory);

  function triggerVisualFeedback(el) {
    el.classList.add('pressed');
    setTimeout(() => el.classList.remove('pressed'), 120);
  }

  // Keyboard Navigation Support
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return;

    if (e.key >= '0' && e.key <= '9') {
      e.preventDefault();
      const btn = document.querySelector(`.key[data-key="${e.key}"]`);
      if (btn) triggerVisualFeedback(btn);
      appendValue(e.key);
    } else if (e.key === '.') {
      e.preventDefault();
      appendValue('.');
    } else if (['+', '-', '*', '/'].includes(e.key)) {
      e.preventDefault();
      const btn = document.querySelector(`.key[data-key="${e.key}"]`);
      if (btn) triggerVisualFeedback(btn);
      appendValue(e.key);
    } else if (e.key === 'Enter' || e.key === '=') {
      e.preventDefault();
      const btn = document.querySelector(`.equals-key`);
      if (btn) triggerVisualFeedback(btn);
      computeResult();
    } else if (e.key === 'Backspace') {
      e.preventDefault();
      triggerVisualFeedback(btnBackspace);
      backspace();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      if (adminModalOverlay && adminModalOverlay.style.display === 'flex') {
        adminModalOverlay.style.display = 'none';
        return;
      }
      triggerVisualFeedback(btnClear);
      clearAll();
    } else if (e.key === 'r' || e.key === 's' || e.key === 'q') {
      e.preventDefault();
      appendValue('sqrt');
    } else if (e.key === '(' || e.key === ')') {
      e.preventDefault();
      appendValue('()');
    } else if (e.key === 'h' || e.key === 'H') {
      e.preventDefault();
      if (historyDrawer.classList.contains('open')) {
        historyDrawer.classList.remove('open');
      } else {
        loadHistory();
        historyDrawer.classList.add('open');
      }
    }
  });

  // Initial display
  updateDisplay();
});
