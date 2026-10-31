/**
 * College Management System - Chart.js Visualizations
 * Provides Department Enrollment Bar Chart, Student Attendance Ring Chart,
 * Subject Performance comparisons, and responsive theme adaptation.
 */

(function () {
  'use strict';

  // Store active chart instances
  const activeCharts = {};

  // Theme helper for chart colors
  function getThemeColors() {
    const isDark = document.documentElement.classList.contains('dark');
    return {
      isDark,
      textColor: isDark ? '#e5e7eb' : '#374151',
      mutedText: isDark ? '#9ca3af' : '#6b7280',
      gridColor: isDark ? 'rgba(75, 85, 99, 0.25)' : 'rgba(229, 231, 235, 0.8)',
      surfaceColor: isDark ? '#1f2937' : '#ffffff',
      primary: '#4f46e5',
      primaryLight: '#818cf8',
      success: '#10b981',
      warning: '#f59e0b',
      danger: '#ef4444'
    };
  }

  // -------------------------------------------------------------
  // 1. Admin Department Bar Chart
  // -------------------------------------------------------------
  function initDeptChart(canvasId = 'deptChart', customData = null) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return null;

    if (activeCharts[canvasId]) {
      activeCharts[canvasId].destroy();
    }

    const theme = getThemeColors();
    const defaultData = {
      labels: ['Computer Science', 'Electronics & Comm', 'Mechanical', 'Civil Eng', 'Electrical', 'Information Tech', 'Biotech'],
      datasets: [
        {
          label: 'Enrolled Students',
          data: [420, 310, 240, 180, 260, 380, 140],
          backgroundColor: [
            'rgba(79, 70, 229, 0.85)',
            'rgba(99, 102, 241, 0.85)',
            'rgba(14, 165, 233, 0.85)',
            'rgba(16, 185, 129, 0.85)',
            'rgba(245, 158, 11, 0.85)',
            'rgba(168, 85, 247, 0.85)',
            'rgba(236, 72, 153, 0.85)'
          ],
          borderColor: [
            '#4338ca',
            '#4f46e5',
            '#0284c7',
            '#059669',
            '#d97706',
            '#9333ea',
            '#db2777'
          ],
          borderWidth: 1.5,
          borderRadius: 8,
          borderSkipped: false
        }
      ]
    };

    const chartData = customData || defaultData;

    const chart = new Chart(canvas, {
      type: 'bar',
      data: chartData,
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            backgroundColor: theme.surfaceColor,
            titleColor: theme.textColor,
            bodyColor: theme.textColor,
            borderColor: theme.gridColor,
            borderWidth: 1,
            padding: 12,
            boxPadding: 6,
            usePointStyle: true,
            callbacks: {
              label: function (context) {
                return ` ${context.parsed.y} Students Enrolled`;
              }
            }
          }
        },
        scales: {
          x: {
            grid: {
              display: false
            },
            ticks: {
              color: theme.mutedText,
              font: {
                family: 'Inter',
                size: 11,
                weight: '500'
              }
            }
          },
          y: {
            grid: {
              color: theme.gridColor
            },
            ticks: {
              color: theme.mutedText,
              font: {
                family: 'Inter',
                size: 11
              },
              stepSize: 100
            },
            beginAtZero: true
          }
        }
      }
    });

    activeCharts[canvasId] = chart;
    return chart;
  }

  // -------------------------------------------------------------
  // 2. Student Attendance Ring Chart
  // -------------------------------------------------------------
  // Plugin to render big percentage text in center of donut
  const centerTextPlugin = {
    id: 'centerTextPlugin',
    afterDraw(chart) {
      if (chart.config.type !== 'doughnut') return;
      const { ctx, chartArea: { width, height, top, left } } = chart;
      ctx.save();
      
      const percentage = chart.config.data.datasets[0].data[0];
      const theme = getThemeColors();

      // Percentage number
      ctx.font = '700 28px Inter, sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = theme.textColor;
      ctx.fillText(`${percentage}%`, left + width / 2, top + height / 2 - 8);

      // Sub-label
      ctx.font = '500 12px Inter, sans-serif';
      ctx.fillStyle = theme.mutedText;
      const label = percentage >= 75 ? 'Optimal' : 'Low Attendance';
      ctx.fillText(label, left + width / 2, top + height / 2 + 16);

      ctx.restore();
    }
  };

  function initAttendanceRing(canvasId = 'attendanceRingChart', percentage = 84) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return null;

    if (activeCharts[canvasId]) {
      activeCharts[canvasId].destroy();
    }

    const theme = getThemeColors();
    const pct = Math.min(100, Math.max(0, Number(percentage) || 0));
    const remainder = 100 - pct;

    let ringColor = theme.success;
    if (pct < 60) {
      ringColor = theme.danger;
    } else if (pct < 75) {
      ringColor = theme.warning;
    }

    const emptyColor = theme.isDark ? '#374151' : '#f3f4f6';

    const chart = new Chart(canvas, {
      type: 'doughnut',
      plugins: [centerTextPlugin],
      data: {
        labels: ['Attended', 'Missed'],
        datasets: [
          {
            data: [pct, remainder],
            backgroundColor: [ringColor, emptyColor],
            borderWidth: 0,
            hoverOffset: 2,
            circumference: 360,
            rotation: -90
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: '78%',
        plugins: {
          legend: {
            display: false
          },
          tooltip: {
            enabled: false
          }
        }
      }
    });

    activeCharts[canvasId] = chart;
    return chart;
  }

  // -------------------------------------------------------------
  // 3. Subject-wise Performance Radar / Bar Chart
  // -------------------------------------------------------------
  function initSubjectPerformanceChart(canvasId = 'subjectPerformanceChart', subjects = [], marks = [], averages = []) {
    const canvas = document.getElementById(canvasId);
    if (!canvas || typeof Chart === 'undefined') return null;

    if (activeCharts[canvasId]) {
      activeCharts[canvasId].destroy();
    }

    const theme = getThemeColors();
    const defaultSubjects = subjects.length ? subjects : ['Data Structures', 'Operating Systems', 'DBMS', 'Algorithms', 'Computer Networks'];
    const defaultMarks = marks.length ? marks : [88, 76, 92, 85, 90];
    const defaultAverages = averages.length ? averages : [72, 68, 75, 71, 78];

    const chart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: defaultSubjects,
        datasets: [
          {
            label: 'Your Marks (%)',
            data: defaultMarks,
            backgroundColor: 'rgba(79, 70, 229, 0.85)',
            borderRadius: 6
          },
          {
            label: 'Class Average (%)',
            data: defaultAverages,
            backgroundColor: theme.isDark ? 'rgba(156, 163, 175, 0.4)' : 'rgba(209, 213, 219, 0.9)',
            borderRadius: 6
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            position: 'top',
            labels: {
              color: theme.textColor,
              font: { family: 'Inter', size: 12 }
            }
          },
          tooltip: {
            backgroundColor: theme.surfaceColor,
            titleColor: theme.textColor,
            bodyColor: theme.textColor,
            borderColor: theme.gridColor,
            borderWidth: 1
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: theme.mutedText, font: { family: 'Inter', size: 11 } }
          },
          y: {
            grid: { color: theme.gridColor },
            ticks: { color: theme.mutedText, font: { family: 'Inter', size: 11 } },
            max: 100,
            beginAtZero: true
          }
        }
      }
    });

    activeCharts[canvasId] = chart;
    return chart;
  }

  // Hook into theme change to re-render charts seamlessly
  window.onThemeChanged = function () {
    if (activeCharts['deptChart']) {
      initDeptChart('deptChart');
    }
    if (activeCharts['attendanceRingChart']) {
      const currentPct = activeCharts['attendanceRingChart'].data.datasets[0].data[0];
      initAttendanceRing('attendanceRingChart', currentPct);
    }
    if (activeCharts['subjectPerformanceChart']) {
      initSubjectPerformanceChart('subjectPerformanceChart');
    }
  };

  // Export functions to window
  window.CMSCharts = {
    initDeptChart,
    initAttendanceRing,
    initSubjectPerformanceChart,
    getThemeColors
  };

})();
