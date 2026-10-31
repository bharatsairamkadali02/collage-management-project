/**
 * College Management System - Core Frontend Application
 * Handles Dark Mode, Socket.IO Real-time Events, Toast Notifications,
 * Modals, and Global Utilities.
 */

(function () {
  'use strict';

  // -------------------------------------------------------------
  // Dark / Light Theme Manager
  // -------------------------------------------------------------
  const THEME_KEY = 'cms_theme';

  function applyTheme(theme) {
    const html = document.documentElement;
    const isDark = theme === 'dark' || (!theme && window.matchMedia('(prefers-color-scheme: dark)').matches);
    
    if (isDark) {
      html.classList.add('dark');
      localStorage.setItem(THEME_KEY, 'dark');
    } else {
      html.classList.remove('dark');
      localStorage.setItem(THEME_KEY, 'light');
    }

    // Update theme toggle icons across the page
    document.querySelectorAll('[data-theme-icon="sun"]').forEach(el => {
      el.classList.toggle('hidden', !isDark);
    });
    document.querySelectorAll('[data-theme-icon="moon"]').forEach(el => {
      el.classList.toggle('hidden', isDark);
    });

    // Notify any active charts to re-color grids/labels
    if (window.onThemeChanged && typeof window.onThemeChanged === 'function') {
      window.onThemeChanged(isDark);
    }
  }

  function toggleTheme() {
    const current = localStorage.getItem(THEME_KEY) || (document.documentElement.classList.contains('dark') ? 'dark' : 'light');
    const target = current === 'dark' ? 'light' : 'dark';
    applyTheme(target);
  }

  // Initialize theme on script run
  const savedTheme = localStorage.getItem(THEME_KEY);
  applyTheme(savedTheme);

  // -------------------------------------------------------------
  // Toast Notification System
  // -------------------------------------------------------------
  function getToastContainer() {
    let container = document.getElementById('toast-container');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toast-container';
      container.className = 'fixed top-5 right-5 z-50 flex flex-col gap-3 pointer-events-none w-full max-w-sm sm:max-w-md';
      document.body.appendChild(container);
    }
    return container;
  }

  const TOAST_ICONS = {
    success: `<svg class="w-5 h-5 text-emerald-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    error: `<svg class="w-5 h-5 text-rose-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`,
    warning: `<svg class="w-5 h-5 text-amber-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"/></svg>`,
    info: `<svg class="w-5 h-5 text-indigo-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>`
  };

  const TOAST_BORDERS = {
    success: 'border-emerald-500/30 dark:border-emerald-500/40',
    error: 'border-rose-500/30 dark:border-rose-500/40',
    warning: 'border-amber-500/30 dark:border-amber-500/40',
    info: 'border-indigo-500/30 dark:border-indigo-500/40'
  };

  function showToast(message, type = 'info', duration = 4000) {
    const container = getToastContainer();
    const toast = document.createElement('div');
    const validTypes = ['success', 'error', 'warning', 'info'];
    const toastType = validTypes.includes(type) ? type : 'info';

    toast.className = `pointer-events-auto flex items-start gap-3 p-4 rounded-xl bg-white dark:bg-gray-800 shadow-xl border ${TOAST_BORDERS[toastType]} transition-all duration-300 toast-enter`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'polite');

    toast.innerHTML = `
      ${TOAST_ICONS[toastType]}
      <div class="flex-1 text-sm font-medium text-gray-800 dark:text-gray-100 leading-snug">
        ${message}
      </div>
      <button type="button" class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 transition-colors p-1" aria-label="Close notification">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
    `;

    const closeBtn = toast.querySelector('button');
    const dismiss = () => {
      toast.classList.remove('toast-enter');
      toast.classList.add('toast-exit');
      setTimeout(() => {
        if (toast.parentElement) toast.remove();
      }, 300);
    };

    closeBtn.addEventListener('click', dismiss);

    container.appendChild(toast);

    if (duration > 0) {
      setTimeout(dismiss, duration);
    }
  }

  // -------------------------------------------------------------
  // CSRF & Fetch Helper
  // -------------------------------------------------------------
  function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  async function fetchWithCSRF(url, options = {}) {
    const headers = options.headers || {};
    const token = getCSRFToken();
    if (token) {
      headers['X-CSRFToken'] = token;
      headers['X-CSRF-Token'] = token;
    }
    return fetch(url, { credentials: 'same-origin', ...options, headers });
  }

  // -------------------------------------------------------------
  // Button Loading State Helper
  // -------------------------------------------------------------
  function setButtonLoading(button, isLoading, loadingText = 'Processing...') {
    if (!button) return;
    if (isLoading) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.classList.add('opacity-75', 'cursor-not-allowed');
      button.innerHTML = `
        <svg class="animate-spin -ml-1 mr-2 h-4 w-4 inline-block text-current" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
        <span>${loadingText}</span>
      `;
    } else {
      button.disabled = false;
      button.classList.remove('opacity-75', 'cursor-not-allowed');
      if (button.dataset.originalHtml) {
        button.innerHTML = button.dataset.originalHtml;
        delete button.dataset.originalHtml;
      }
    }
  }

  // -------------------------------------------------------------
  // Modal System
  // -------------------------------------------------------------
  function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
    document.body.classList.add('overflow-hidden');

    const focusable = modal.querySelector('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    if (focusable) focusable.focus();
  }

  function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (!modal) return;
    modal.classList.add('hidden');
    modal.classList.remove('flex');
    document.body.classList.remove('overflow-hidden');
  }

  function showConfirmModal({
    title = 'Confirm Action',
    message = 'Are you sure you want to proceed?',
    confirmText = 'Confirm',
    cancelText = 'Cancel',
    confirmClass = 'bg-rose-600 hover:bg-rose-700 text-white',
    onConfirm = () => {}
  }) {
    const modal = document.getElementById('confirm-modal');
    if (!modal) {
      if (confirm(message)) onConfirm();
      return;
    }

    const titleEl = modal.querySelector('[data-confirm-title]');
    const messageEl = modal.querySelector('[data-confirm-message]');
    const confirmBtn = modal.querySelector('[data-confirm-btn]');
    const cancelBtn = modal.querySelector('[data-cancel-btn]');

    if (titleEl) titleEl.textContent = title;
    if (messageEl) messageEl.textContent = message;
    if (confirmBtn) {
      confirmBtn.textContent = confirmText;
      confirmBtn.className = `px-4 py-2 text-sm font-semibold rounded-lg shadow-sm focus:outline-none focus:ring-2 focus:ring-offset-2 transition-all ${confirmClass}`;
      
      // Remove previous listener clones
      const newConfirmBtn = confirmBtn.cloneNode(true);
      confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
      
      newConfirmBtn.addEventListener('click', async () => {
        try {
          setButtonLoading(newConfirmBtn, true, 'Working...');
          await onConfirm();
        } finally {
          setButtonLoading(newConfirmBtn, false);
          closeModal('confirm-modal');
        }
      });
    }

    if (cancelBtn) {
      cancelBtn.onclick = () => closeModal('confirm-modal');
    }

    openModal('confirm-modal');
  }

  // -------------------------------------------------------------
  // Mobile Sidebar Drawer
  // -------------------------------------------------------------
  function setupMobileSidebar() {
    const toggleBtn = document.getElementById('mobile-sidebar-toggle');
    const closeBtn = document.getElementById('mobile-sidebar-close');
    const sidebar = document.getElementById('main-sidebar');
    const backdrop = document.getElementById('sidebar-backdrop');

    function openSidebar() {
      if (!sidebar) return;
      sidebar.classList.remove('-translate-x-full');
      if (backdrop) backdrop.classList.remove('hidden');
      document.body.classList.add('overflow-hidden', 'lg:overflow-auto');
    }

    function closeSidebar() {
      if (!sidebar) return;
      sidebar.classList.add('-translate-x-full');
      if (backdrop) backdrop.classList.add('hidden');
      document.body.classList.remove('overflow-hidden', 'lg:overflow-auto');
    }

    if (toggleBtn) toggleBtn.addEventListener('click', openSidebar);
    if (closeBtn) closeBtn.addEventListener('click', closeSidebar);
    if (backdrop) backdrop.addEventListener('click', closeSidebar);
  }

  // -------------------------------------------------------------
  // Socket.IO Real-time Connection & Events
  // -------------------------------------------------------------
  function initSocketIO() {
    if (typeof io === 'undefined') {
      console.warn('Socket.IO client library not loaded.');
      return;
    }

    try {
      const socket = io({
        transports: ['websocket', 'polling'],
        reconnectionAttempts: 5,
        reconnectionDelay: 1000
      });

      window.cmsSocket = socket;

      socket.on('connect', () => {
        console.log('Real-time connection established via Socket.IO');
        document.querySelectorAll('[data-connection-status]').forEach(el => {
          el.classList.remove('bg-gray-400', 'bg-rose-500');
          el.classList.add('bg-emerald-500');
        });
      });

      socket.on('disconnect', () => {
        document.querySelectorAll('[data-connection-status]').forEach(el => {
          el.classList.remove('bg-emerald-500');
          el.classList.add('bg-rose-500');
        });
      });

      // 1. Attendance update event
      socket.on('attendance_updated', (data) => {
        const msg = data && data.message ? data.message : `Attendance updated for ${data?.course || 'course'}`;
        showToast(msg, 'info');
        if (window.onAttendanceUpdated && typeof window.onAttendanceUpdated === 'function') {
          window.onAttendanceUpdated(data);
        }
      });

      // 2. Result update event
      socket.on('result_updated', (data) => {
        const msg = data && data.message ? data.message : 'New semester results have been published!';
        showToast(msg, 'success');
        if (window.onResultsUpdated && typeof window.onResultsUpdated === 'function') {
          window.onResultsUpdated(data);
        }
      });

      // 3. Exam status change
      socket.on('exam_status_changed', (data) => {
        const msg = data && data.message ? data.message : `Exam "${data?.exam_title || 'Exam'}" status changed to ${data?.status || 'updated'}`;
        showToast(msg, 'warning');
        if (window.onExamStatusChanged && typeof window.onExamStatusChanged === 'function') {
          window.onExamStatusChanged(data);
        }
      });

      // 4. Live Dashboard stats
      socket.on('dashboard_stats', (stats) => {
        if (!stats) return;
        Object.entries(stats).forEach(([key, val]) => {
          document.querySelectorAll(`[data-stat="${key}"]`).forEach(el => {
            el.textContent = val;
            el.classList.add('transition-transform', 'scale-110');
            setTimeout(() => el.classList.remove('scale-110'), 300);
          });
        });
      });

      // 5. Live Online Users count
      socket.on('online_users', (data) => {
        const count = typeof data === 'object' ? data.count : data;
        document.querySelectorAll('[data-online-users]').forEach(el => {
          el.textContent = count;
        });
      });

    } catch (err) {
      console.error('Socket.IO initialization error:', err);
    }
  }

  // -------------------------------------------------------------
  // Document Ready Initialization
  // -------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    // Theme toggles
    document.querySelectorAll('[data-theme-toggle]').forEach(btn => {
      btn.addEventListener('click', toggleTheme);
    });

    // Mobile sidebar
    setupMobileSidebar();

    // Init Socket
    initSocketIO();

    // Auto dismiss flash messages from server if present
    document.querySelectorAll('.flash-message').forEach(flash => {
      setTimeout(() => {
        flash.classList.add('opacity-0', 'transition-opacity', 'duration-500');
        setTimeout(() => flash.remove(), 500);
      }, 5000);
    });

    // Global keyboard shortcut: Ctrl+K or Cmd+K for quick search focus
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        const searchInput = document.getElementById('global-search-input');
        if (searchInput) searchInput.focus();
      }
    });
  });

  // Export public API to window
  window.CMS = {
    showToast,
    toggleTheme,
    applyTheme,
    openModal,
    closeModal,
    showConfirmModal,
    setButtonLoading,
    fetchWithCSRF,
    getCSRFToken
  };

})();
