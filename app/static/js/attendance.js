/**
 * College Management System - Attendance Module
 * Handles Faculty Attendance Marking Grid, Toggles (Present/Late/Absent),
 * Mark All Bulk Actions, Live Summary Counters, and Async Submission.
 */

(function () {
  'use strict';

  class AttendanceManager {
    constructor() {
      this.table = document.getElementById('attendance-table');
      this.form = document.getElementById('attendance-form');
      this.rows = [];
      this.counts = { present: 0, late: 0, absent: 0, total: 0 };

      this.init();
    }

    init() {
      if (!this.table && !this.form) return;

      this.cacheRows();
      this.bindEvents();
      this.updateCounters();
    }

    cacheRows() {
      const rowElements = document.querySelectorAll('[data-attendance-row]');
      this.rows = Array.from(rowElements).map(row => {
        const studentId = row.dataset.studentId;
        const presentBtn = row.querySelector('[data-status-btn="present"]');
        const lateBtn = row.querySelector('[data-status-btn="late"]');
        const absentBtn = row.querySelector('[data-status-btn="absent"]');
        const statusInput = row.querySelector(`input[name="status_${studentId}"]`) || row.querySelector('.status-input');
        const remarksInput = row.querySelector(`input[name="remarks_${studentId}"]`) || row.querySelector('.remarks-input');

        return {
          element: row,
          studentId,
          presentBtn,
          lateBtn,
          absentBtn,
          statusInput,
          remarksInput,
          currentStatus: statusInput ? statusInput.value : 'present'
        };
      });

      this.counts.total = this.rows.length;
    }

    bindEvents() {
      // Toggle button clicks
      this.rows.forEach(item => {
        if (item.presentBtn) {
          item.presentBtn.addEventListener('click', () => this.setStatus(item, 'present'));
        }
        if (item.lateBtn) {
          item.lateBtn.addEventListener('click', () => this.setStatus(item, 'late'));
        }
        if (item.absentBtn) {
          item.absentBtn.addEventListener('click', () => this.setStatus(item, 'absent'));
        }
      });

      // Mark All Present
      const markAllPresentBtn = document.getElementById('btn-mark-all-present');
      if (markAllPresentBtn) {
        markAllPresentBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.markAll('present');
          if (window.CMS) window.CMS.showToast('Marked all students as Present', 'info');
        });
      }

      // Mark All Absent
      const markAllAbsentBtn = document.getElementById('btn-mark-all-absent');
      if (markAllAbsentBtn) {
        markAllAbsentBtn.addEventListener('click', (e) => {
          e.preventDefault();
          this.markAll('absent');
          if (window.CMS) window.CMS.showToast('Marked all students as Absent', 'warning');
        });
      }

      // Live search filter in attendance table
      const searchInput = document.getElementById('attendance-search');
      if (searchInput) {
        searchInput.addEventListener('input', (e) => {
          const query = e.target.value.toLowerCase().trim();
          this.filterRows(query);
        });
      }

      // Form submission
      if (this.form) {
        this.form.addEventListener('submit', (e) => this.handleSubmit(e));
      }
    }

    setStatus(item, status) {
      item.currentStatus = status;
      if (item.statusInput) {
        item.statusInput.value = status;
      }

      // Style buttons accordingly
      const activeClasses = {
        present: 'bg-emerald-600 text-white shadow-sm hover:bg-emerald-700',
        late: 'bg-amber-500 text-white shadow-sm hover:bg-amber-600',
        absent: 'bg-rose-600 text-white shadow-sm hover:bg-rose-700'
      };

      const inactiveClasses = 'bg-gray-100 dark:bg-gray-700/60 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600';

      [
        { type: 'present', btn: item.presentBtn },
        { type: 'late', btn: item.lateBtn },
        { type: 'absent', btn: item.absentBtn }
      ].forEach(({ type, btn }) => {
        if (!btn) return;
        // Strip active classes
        Object.values(activeClasses).forEach(cls => {
          cls.split(' ').forEach(c => btn.classList.remove(c));
        });
        inactiveClasses.split(' ').forEach(c => btn.classList.remove(c));

        if (type === status) {
          activeClasses[type].split(' ').forEach(c => btn.classList.add(c));
          btn.setAttribute('aria-pressed', 'true');
        } else {
          inactiveClasses.split(' ').forEach(c => btn.classList.add(c));
          btn.setAttribute('aria-pressed', 'false');
        }
      });

      this.updateCounters();
    }

    markAll(status) {
      this.rows.forEach(item => {
        // Only update currently visible rows if filtered
        if (item.element.offsetParent !== null) {
          this.setStatus(item, status);
        }
      });
    }

    filterRows(query) {
      let visibleCount = 0;
      this.rows.forEach(item => {
        const text = item.element.textContent.toLowerCase();
        const matches = text.includes(query);
        item.element.style.display = matches ? '' : 'none';
        if (matches) visibleCount++;
      });

      const emptyEl = document.getElementById('attendance-empty-search');
      if (emptyEl) {
        emptyEl.classList.toggle('hidden', visibleCount > 0);
      }
    }

    updateCounters() {
      let present = 0;
      let late = 0;
      let absent = 0;

      this.rows.forEach(item => {
        if (item.currentStatus === 'present') present++;
        else if (item.currentStatus === 'late') late++;
        else if (item.currentStatus === 'absent') absent++;
      });

      this.counts = { present, late, absent, total: this.rows.length };

      const presentEl = document.getElementById('stat-present-count');
      const lateEl = document.getElementById('stat-late-count');
      const absentEl = document.getElementById('stat-absent-count');
      const totalEl = document.getElementById('stat-total-count');
      const pctEl = document.getElementById('stat-attendance-pct');

      if (presentEl) presentEl.textContent = present;
      if (lateEl) lateEl.textContent = late;
      if (absentEl) absentEl.textContent = absent;
      if (totalEl) totalEl.textContent = this.counts.total;

      if (pctEl && this.counts.total > 0) {
        const rate = Math.round(((present + (late * 0.5)) / this.counts.total) * 100);
        pctEl.textContent = `${rate}%`;
      }
    }

    async handleSubmit(e) {
      e.preventDefault();
      const submitBtn = this.form.querySelector('button[type="submit"]');

      const attendanceData = this.rows.map(r => ({
        student_id: r.studentId,
        status: r.currentStatus,
        remarks: r.remarksInput ? r.remarksInput.value : ''
      }));

      const courseId = this.form.querySelector('[name="course_id"]')?.value || '';
      const date = this.form.querySelector('[name="date"]')?.value || new Date().toISOString().split('T')[0];
      const semester = this.form.querySelector('[name="semester"]')?.value || '';

      const payload = {
        course_id: courseId,
        date: date,
        semester: semester,
        attendance: attendanceData
      };

      if (window.CMS) {
        window.CMS.setButtonLoading(submitBtn, true, 'Submitting Attendance...');
      }

      try {
        const actionUrl = this.form.getAttribute('action') || window.location.href;
        const res = await (window.CMS ? window.CMS.fetchWithCSRF : fetch)(actionUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });

        if (!res.ok) {
          throw new Error(`Server returned ${res.status}`);
        }

        const data = await res.json().catch(() => ({}));

        if (window.CMS) {
          window.CMS.showToast('Attendance recorded and synced successfully!', 'success');
        }

        // Emit Socket event to update connected clients if client socket is available
        if (window.cmsSocket && window.cmsSocket.connected) {
          window.cmsSocket.emit('attendance_updated', {
            course: courseId,
            date: date,
            message: `Attendance marked for course ${courseId}`
          });
        }
      } catch (err) {
        console.error('Failed to submit attendance:', err);
        if (window.CMS) {
          window.CMS.showToast('Failed to save attendance. Please retry.', 'error');
        }
      } finally {
        if (window.CMS) {
          window.CMS.setButtonLoading(submitBtn, false);
        }
      }
    }

    // Skeleton loader toggle when course/date changes
    showSkeleton(loading = true) {
      const skeletonContainer = document.getElementById('attendance-skeleton');
      const tableContainer = document.getElementById('attendance-table-container');

      if (skeletonContainer && tableContainer) {
        if (loading) {
          skeletonContainer.classList.remove('hidden');
          tableContainer.classList.add('hidden');
        } else {
          skeletonContainer.classList.add('hidden');
          tableContainer.classList.remove('hidden');
        }
      }
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    window.attendanceManager = new AttendanceManager();
  });

})();
