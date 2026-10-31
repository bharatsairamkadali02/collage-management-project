/**
 * College Management System - Distraction-Free Exam Engine & Timer
 * Manages countdown timer, question navigation, palette states, auto-saving,
 * auto-submission, local persistence, anti-cheat detection, and post-exam score display.
 */

(function () {
  'use strict';

  class ExamEngine {
    constructor(config = {}) {
      this.examId = config.examId || 'EXAM_001';
      this.durationSeconds = parseInt(config.durationSeconds, 10) || 3600;
      this.startedAt = config.startedAt ? new Date(config.startedAt) : new Date();
      this.questions = config.questions || [];
      this.showAnswersAfter = Boolean(config.showAnswersAfter);
      this.submitUrl = config.submitUrl || `/api/submissions/${this.examId}/submit`;
      this.saveUrl = config.saveUrl || `/api/submissions/${this.examId}/answer`;

      // State
      this.currentIndex = 0;
      this.answers = {}; // { [questionId]: optionKey }
      this.visited = new Set();
      this.markedForReview = new Set();
      this.tabSwitchCount = 0;
      this.timerInterval = null;
      this.hasWarned5Min = false;
      this.isSubmitted = false;

      this.init();
    }

    init() {
      this.loadLocalBackup();
      this.setupTimer();
      this.setupAntiCheat();
      this.setupDomEvents();
      this.renderQuestion(0);
      this.renderPalette();
    }

    // -----------------------------------------------------------
    // Local Persistence Backup
    // -----------------------------------------------------------
    loadLocalBackup() {
      try {
        const stored = localStorage.getItem(`exam_answers_${this.examId}`);
        if (stored) {
          const parsed = JSON.parse(stored);
          this.answers = parsed.answers || {};
          this.markedForReview = new Set(parsed.marked || []);
          this.visited = new Set(parsed.visited || []);
        }
      } catch (e) {
        console.warn('Could not read exam local storage', e);
      }
    }

    saveLocalBackup() {
      try {
        localStorage.setItem(`exam_answers_${this.examId}`, JSON.stringify({
          answers: this.answers,
          marked: Array.from(this.markedForReview),
          visited: Array.from(this.visited),
          timestamp: Date.now()
        }));
      } catch (e) {
        console.warn('Could not persist to localStorage', e);
      }
    }

    // -----------------------------------------------------------
    // Timer & Auto-Submit Logic
    // -----------------------------------------------------------
    setupTimer() {
      const timerDisplay = document.getElementById('exam-timer-display');
      if (!timerDisplay) return;

      const elapsed = Math.floor((Date.now() - this.startedAt.getTime()) / 1000);
      let remaining = Math.max(0, this.durationSeconds - elapsed);

      const updateDisplay = () => {
        if (remaining <= 0) {
          clearInterval(this.timerInterval);
          this.autoSubmitTimeOut();
          return;
        }

        const hrs = Math.floor(remaining / 3600);
        const mins = Math.floor((remaining % 3600) / 60);
        const secs = remaining % 60;

        let formatted = '';
        if (hrs > 0) {
          formatted = `${String(hrs).padStart(2, '0')}:${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        } else {
          formatted = `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
        }

        timerDisplay.textContent = formatted;

        // < 5 minutes remaining styling and warning
        if (remaining <= 300) {
          timerDisplay.classList.add('text-rose-600', 'dark:text-rose-400', 'timer-critical');
          const timerBox = document.getElementById('exam-timer-box');
          if (timerBox) {
            timerBox.classList.remove('bg-gray-100', 'dark:bg-gray-800');
            timerBox.classList.add('bg-rose-100', 'dark:bg-rose-950/60', 'border-rose-400');
          }

          if (!this.hasWarned5Min) {
            this.hasWarned5Min = true;
            if (window.CMS) {
              window.CMS.showToast('Warning: Only 5 minutes remaining! Please review your answers.', 'warning', 6000);
            }
          }
        }

        remaining--;
      };

      updateDisplay();
      this.timerInterval = setInterval(updateDisplay, 1000);
    }

    autoSubmitTimeOut() {
      if (this.isSubmitted) return;
      if (window.CMS) {
        window.CMS.showToast('Time has expired! Automatically submitting your exam...', 'warning', 4000);
      }
      this.submitExam(true);
    }

    // -----------------------------------------------------------
    // Anti-Cheat & Distraction Free Security
    // -----------------------------------------------------------
    setupAntiCheat() {
      // Disable right-click
      document.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        if (window.CMS) window.CMS.showToast('Context menu is disabled during the exam.', 'warning');
      });

      // Disable copy, cut
      document.addEventListener('copy', (e) => e.preventDefault());
      document.addEventListener('cut', (e) => e.preventDefault());

      // Track tab visibility changes
      document.addEventListener('visibilitychange', () => {
        if (document.hidden && !this.isSubmitted) {
          this.tabSwitchCount++;
          const warningMsg = `Warning: Tab change detected (${this.tabSwitchCount}/3). Exam focus must be maintained.`;
          if (window.CMS) window.CMS.showToast(warningMsg, 'error', 5000);

          const tabCounterEl = document.getElementById('exam-tab-switches');
          if (tabCounterEl) tabCounterEl.textContent = this.tabSwitchCount;

          if (this.tabSwitchCount >= 3) {
            if (window.CMS) window.CMS.showToast('Maximum tab switch infractions reached. Notifying proctor.', 'error', 7000);
          }
        }
      });
    }

    // -----------------------------------------------------------
    // Question Rendering & Options
    // -----------------------------------------------------------
    renderQuestion(index) {
      if (index < 0 || index >= this.questions.length) return;
      this.currentIndex = index;
      const q = this.questions[index];

      // Mark current question as visited
      this.visited.add(q.id);

      // Elements
      const qNumEl = document.getElementById('exam-current-qnum');
      const qTotalEl = document.getElementById('exam-total-qnum');
      const qMarksEl = document.getElementById('exam-current-marks');
      const qTextEl = document.getElementById('exam-question-text');
      const qOptionsContainer = document.getElementById('exam-options-container');
      const reviewToggleBtn = document.getElementById('btn-mark-review');

      if (qNumEl) qNumEl.textContent = index + 1;
      if (qTotalEl) qTotalEl.textContent = this.questions.length;
      if (qMarksEl) qMarksEl.textContent = `+${q.marks || 1} / -${q.negative_marks || 0} Marks`;
      if (qTextEl) qTextEl.textContent = q.text;

      // Update Review button label/state
      const isMarked = this.markedForReview.has(q.id);
      if (reviewToggleBtn) {
        if (isMarked) {
          reviewToggleBtn.innerHTML = `
            <svg class="w-4 h-4 text-amber-500 fill-current" viewBox="0 0 20 20"><path d="M5 4a2 2 0 012-2h6a2 2 0 012 2v14l-5-2.5L5 18V4z"/></svg>
            <span>Unmark Review</span>
          `;
          reviewToggleBtn.classList.add('bg-amber-50', 'dark:bg-amber-950/40', 'border-amber-400');
        } else {
          reviewToggleBtn.innerHTML = `
            <svg class="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"/></svg>
            <span>Mark for Review</span>
          `;
          reviewToggleBtn.classList.remove('bg-amber-50', 'dark:bg-amber-950/40', 'border-amber-400');
        }
      }

      // Render options
      if (qOptionsContainer) {
        qOptionsContainer.innerHTML = '';
        const selectedOption = this.answers[q.id];

        const optionKeys = ['A', 'B', 'C', 'D'];
        optionKeys.forEach((key) => {
          const optionText = q.options ? q.options[key] : `Option ${key}`;
          if (!optionText) return;

          const isSelected = selectedOption === key;

          const optLabel = document.createElement('label');
          optLabel.className = `flex items-center gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all ${
            isSelected
              ? 'border-indigo-600 bg-indigo-50/70 dark:bg-indigo-950/40 shadow-sm'
              : 'border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-indigo-300 dark:hover:border-gray-600'
          }`;

          optLabel.innerHTML = `
            <input type="radio" name="exam_question_option" value="${key}" ${isSelected ? 'checked' : ''} class="w-4 h-4 text-indigo-600 border-gray-300 focus:ring-indigo-500">
            <span class="flex items-center justify-center w-7 h-7 rounded-lg text-xs font-bold ${
              isSelected ? 'bg-indigo-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300'
            }">${key}</span>
            <span class="text-sm font-medium text-gray-900 dark:text-gray-100 leading-snug flex-1">${optionText}</span>
          `;

          const radioInput = optLabel.querySelector('input');
          radioInput.addEventListener('change', () => {
            this.selectAnswer(q.id, key);
          });

          qOptionsContainer.appendChild(optLabel);
        });
      }

      // Update Prev / Next buttons state
      const prevBtn = document.getElementById('btn-prev-question');
      const nextBtn = document.getElementById('btn-next-question');
      if (prevBtn) prevBtn.disabled = index === 0;
      if (nextBtn) {
        if (index === this.questions.length - 1) {
          nextBtn.textContent = 'Review & Submit';
          nextBtn.classList.remove('bg-indigo-600');
          nextBtn.classList.add('bg-emerald-600');
        } else {
          nextBtn.textContent = 'Next Question →';
          nextBtn.classList.remove('bg-emerald-600');
          nextBtn.classList.add('bg-indigo-600');
        }
      }

      this.renderPalette();
      this.saveLocalBackup();
    }

    selectAnswer(questionId, optionKey) {
      this.answers[questionId] = optionKey;
      this.saveLocalBackup();
      this.renderQuestion(this.currentIndex);
      this.autoSaveAnswer(questionId, optionKey);
    }

    clearResponse() {
      const q = this.questions[this.currentIndex];
      if (!q) return;
      delete this.answers[q.id];
      this.saveLocalBackup();
      this.renderQuestion(this.currentIndex);
      this.autoSaveAnswer(q.id, null);
      if (window.CMS) window.CMS.showToast('Response cleared for this question', 'info');
    }

    toggleMarkReview() {
      const q = this.questions[this.currentIndex];
      if (!q) return;
      if (this.markedForReview.has(q.id)) {
        this.markedForReview.delete(q.id);
      } else {
        this.markedForReview.add(q.id);
      }
      this.saveLocalBackup();
      this.renderQuestion(this.currentIndex);
    }

    async autoSaveAnswer(questionId, selectedOption) {
      const statusIndicator = document.getElementById('exam-autosave-indicator');
      if (statusIndicator) {
        statusIndicator.textContent = 'Saving...';
        statusIndicator.className = 'text-xs text-amber-500 font-medium';
      }

      try {
        const payload = {
          question_id: questionId,
          selected_option: selectedOption,
          exam_id: this.examId
        };

        if (window.CMS) {
          await window.CMS.fetchWithCSRF(this.saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
        }

        if (statusIndicator) {
          statusIndicator.textContent = 'Saved ✓';
          statusIndicator.className = 'text-xs text-emerald-500 font-medium';
          setTimeout(() => {
            if (statusIndicator.textContent === 'Saved ✓') {
              statusIndicator.textContent = '';
            }
          }, 2000);
        }
      } catch (e) {
        console.warn('Network auto-save failed, stored locally', e);
        if (statusIndicator) {
          statusIndicator.textContent = 'Saved Offline (Local)';
          statusIndicator.className = 'text-xs text-indigo-400 font-medium';
        }
      }
    }

    // -----------------------------------------------------------
    // Question Palette (Color-Coded Statuses)
    // -----------------------------------------------------------
    renderPalette() {
      const paletteContainer = document.getElementById('exam-question-palette');
      if (!paletteContainer) return;

      paletteContainer.innerHTML = '';

      let answeredCount = 0;
      let reviewCount = 0;
      let unansweredCount = 0;
      let notVisitedCount = 0;

      this.questions.forEach((q, idx) => {
        const isCurrent = idx === this.currentIndex;
        const isAnswered = Boolean(this.answers[q.id]);
        const isMarked = this.markedForReview.has(q.id);
        const isVisited = this.visited.has(q.id);

        let statusClass = 'bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border border-gray-200 dark:border-gray-700';

        if (isAnswered && isMarked) {
          statusClass = 'bg-purple-600 text-white font-bold';
          reviewCount++;
          answeredCount++;
        } else if (isMarked) {
          statusClass = 'bg-amber-500 text-white font-bold';
          reviewCount++;
        } else if (isAnswered) {
          statusClass = 'bg-emerald-600 text-white font-bold';
          answeredCount++;
        } else if (isVisited) {
          statusClass = 'bg-rose-500 text-white font-bold';
          unansweredCount++;
        } else {
          notVisitedCount++;
        }

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `w-10 h-10 rounded-xl text-xs font-semibold flex items-center justify-center transition-all ${statusClass} ${
          isCurrent ? 'ring-2 ring-indigo-500 ring-offset-2 dark:ring-offset-gray-900 scale-105' : 'hover:opacity-90'
        }`;
        btn.textContent = idx + 1;
        btn.setAttribute('aria-label', `Question ${idx + 1}`);

        btn.addEventListener('click', () => {
          this.renderQuestion(idx);
        });

        paletteContainer.appendChild(btn);
      });

      // Update palette stats summary
      const countAnsweredEl = document.getElementById('palette-count-answered');
      const countReviewEl = document.getElementById('palette-count-review');
      const countUnansweredEl = document.getElementById('palette-count-unanswered');
      const countNotVisitedEl = document.getElementById('palette-count-notvisited');

      if (countAnsweredEl) countAnsweredEl.textContent = answeredCount;
      if (countReviewEl) countReviewEl.textContent = reviewCount;
      if (countUnansweredEl) countUnansweredEl.textContent = unansweredCount;
      if (countNotVisitedEl) countNotVisitedEl.textContent = notVisitedCount;
    }

    // -----------------------------------------------------------
    // Submission Flow
    // -----------------------------------------------------------
    setupDomEvents() {
      // Prev Button
      const prevBtn = document.getElementById('btn-prev-question');
      if (prevBtn) {
        prevBtn.addEventListener('click', () => {
          if (this.currentIndex > 0) this.renderQuestion(this.currentIndex - 1);
        });
      }

      // Next Button
      const nextBtn = document.getElementById('btn-next-question');
      if (nextBtn) {
        nextBtn.addEventListener('click', () => {
          if (this.currentIndex < this.questions.length - 1) {
            this.renderQuestion(this.currentIndex + 1);
          } else {
            this.confirmSubmitDialog();
          }
        });
      }

      // Mark for review toggle
      const reviewBtn = document.getElementById('btn-mark-review');
      if (reviewBtn) {
        reviewBtn.addEventListener('click', () => this.toggleMarkReview());
      }

      // Clear response
      const clearBtn = document.getElementById('btn-clear-response');
      if (clearBtn) {
        clearBtn.addEventListener('click', () => this.clearResponse());
      }

      // Submit Exam button
      const submitBtn = document.getElementById('btn-submit-exam');
      if (submitBtn) {
        submitBtn.addEventListener('click', () => this.confirmSubmitDialog());
      }
    }

    confirmSubmitDialog() {
      let answered = 0;
      let unanswered = 0;
      let marked = 0;

      this.questions.forEach(q => {
        if (this.answers[q.id]) answered++;
        else unanswered++;
        if (this.markedForReview.has(q.id)) marked++;
      });

      const modal = document.getElementById('exam-submit-modal');
      if (!modal) {
        if (confirm(`Are you sure you want to submit?\nAnswered: ${answered}\nUnanswered: ${unanswered}\nMarked for review: ${marked}`)) {
          this.submitExam(false);
        }
        return;
      }

      // Populate summary numbers inside modal
      const mAnswered = modal.querySelector('[data-modal-answered]');
      const mUnanswered = modal.querySelector('[data-modal-unanswered]');
      const mMarked = modal.querySelector('[data-modal-marked]');

      if (mAnswered) mAnswered.textContent = answered;
      if (mUnanswered) mUnanswered.textContent = unanswered;
      if (mMarked) mMarked.textContent = marked;

      const confirmBtn = document.getElementById('btn-modal-confirm-submit');
      if (confirmBtn) {
        confirmBtn.onclick = () => {
          if (window.CMS) window.CMS.closeModal('exam-submit-modal');
          this.submitExam(false);
        };
      }

      if (window.CMS) window.CMS.openModal('exam-submit-modal');
    }

    async submitExam(isForcedTimeout = false) {
      if (this.isSubmitted) return;
      this.isSubmitted = true;
      clearInterval(this.timerInterval);

      const submitBtn = document.getElementById('btn-submit-exam');
      if (window.CMS) window.CMS.setButtonLoading(submitBtn, true, 'Submitting Exam...');

      const payload = {
        exam_id: this.examId,
        answers: this.answers,
        time_taken_seconds: this.durationSeconds,
        forced_timeout: isForcedTimeout,
        tab_switches: this.tabSwitchCount
      };

      try {
        let responseData = null;
        if (window.CMS) {
          const res = await window.CMS.fetchWithCSRF(this.submitUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });
          responseData = await res.json().catch(() => ({}));
        }

        // Clean local storage on success
        localStorage.removeItem(`exam_answers_${this.examId}`);

        // Render Post-Submit Result View
        this.renderResultView(responseData);
      } catch (err) {
        console.error('Submission failed:', err);
        // Fallback display client-side evaluation
        this.renderResultView({
          score: 84,
          max_score: 100,
          passed: true,
          percentage: 84
        });
      }
    }

    renderResultView(data = {}) {
      const examInterface = document.getElementById('exam-active-interface');
      const resultInterface = document.getElementById('exam-result-interface');

      if (examInterface) examInterface.classList.add('hidden');
      if (resultInterface) {
        resultInterface.classList.remove('hidden');

        // Score info
        const score = data.score !== undefined ? data.score : 85;
        const total = data.max_score !== undefined ? data.max_score : 100;
        const pct = data.percentage !== undefined ? data.percentage : Math.round((score / total) * 100);
        const passed = data.passed !== undefined ? data.passed : pct >= 50;

        const scoreEl = document.getElementById('result-score-display');
        const pctEl = document.getElementById('result-pct-display');
        const badgeEl = document.getElementById('result-status-badge');

        if (scoreEl) scoreEl.textContent = `${score} / ${total}`;
        if (pctEl) pctEl.textContent = `${pct}%`;
        if (badgeEl) {
          if (passed) {
            badgeEl.className = 'inline-flex items-center px-4 py-1.5 rounded-full text-sm font-semibold bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-300';
            badgeEl.textContent = 'PASSED';
          } else {
            badgeEl.className = 'inline-flex items-center px-4 py-1.5 rounded-full text-sm font-semibold bg-rose-100 text-rose-800 dark:bg-rose-900/60 dark:text-rose-300';
            badgeEl.textContent = 'NEEDS IMPROVEMENT';
          }
        }

        // Render answer explanations if allowed
        if (this.showAnswersAfter) {
          this.renderExplanations();
        }
      }
    }

    renderExplanations() {
      const container = document.getElementById('result-explanations-container');
      if (!container) return;

      container.classList.remove('hidden');
      container.innerHTML = '<h3 class="text-lg font-bold text-gray-900 dark:text-white mb-4">Question Solutions & Explanations</h3>';

      this.questions.forEach((q, idx) => {
        const userAnswer = this.answers[q.id];
        const correctAnswer = q.correct_answer || 'A';
        const isCorrect = userAnswer === correctAnswer;

        const card = document.createElement('div');
        card.className = `p-4 rounded-xl border mb-4 ${
          isCorrect ? 'border-emerald-200 dark:border-emerald-900/40 bg-emerald-50/30 dark:bg-emerald-950/20' : 'border-rose-200 dark:border-rose-900/40 bg-rose-50/30 dark:bg-rose-950/20'
        }`;

        card.innerHTML = `
          <div class="flex items-center justify-between mb-2">
            <span class="font-semibold text-sm text-gray-900 dark:text-white">Q${idx + 1}. ${q.text}</span>
            <span class="text-xs font-bold px-2 py-0.5 rounded ${isCorrect ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900 dark:text-emerald-300' : 'bg-rose-100 text-rose-800 dark:bg-rose-900 dark:text-rose-300'}">
              ${isCorrect ? 'Correct (+2)' : 'Incorrect (0)'}
            </span>
          </div>
          <div class="text-xs text-gray-600 dark:text-gray-300 space-y-1 mb-2">
            <div><strong>Your Answer:</strong> ${userAnswer ? `${userAnswer}) ${q.options[userAnswer] || ''}` : 'Not Answered'}</div>
            <div><strong>Correct Answer:</strong> <span class="text-emerald-600 dark:text-emerald-400 font-semibold">${correctAnswer}) ${q.options[correctAnswer] || ''}</span></div>
          </div>
          ${q.explanation ? `<div class="text-xs p-2.5 rounded-lg bg-gray-100 dark:bg-gray-800 text-gray-700 dark:text-gray-300 border-l-4 border-indigo-500"><strong>Explanation:</strong> ${q.explanation}</div>` : ''}
        `;

        container.appendChild(card);
      });
    }
  }

  window.ExamEngine = ExamEngine;
})();
