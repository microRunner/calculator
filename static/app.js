document.addEventListener('DOMContentLoaded', () => {
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
      localStorage.setItem(STORAGE_KEY, JSON.stringify(history.slice(0, 50)));
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
        body: JSON.stringify({ expression: expr })
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
  function loadHistory() {
    try {
      const data = getLocalHistory();
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
