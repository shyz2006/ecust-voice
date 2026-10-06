(function () {
    'use strict';

    const STATUS_LABELS = {
        running: '运行中',
        starting: '启动中',
        stopped: '待命',
        error: '异常'
    };

    const WORKFLOW_APPS = ['insight', 'media', 'query', 'report'];
    const modalReturnFocus = new WeakMap();

    function ready(callback) {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', callback, { once: true });
        } else {
            callback();
        }
    }

    function getIndicatorState(indicator) {
        if (!indicator) return 'stopped';
        if (indicator.classList.contains('running')) return 'running';
        if (indicator.classList.contains('starting')) return 'starting';
        if (indicator.classList.contains('error')) return 'error';
        return 'stopped';
    }

    function syncWorkflowStatus(app) {
        const indicator = document.getElementById(`status-${app}`);
        const item = document.querySelector(`[data-workflow-app="${app}"]`);
        const text = document.getElementById(`workflow-${app}-state`);
        const button = document.querySelector(`.app-button[data-app="${app}"]`);
        const state = getIndicatorState(indicator);

        if (item) item.dataset.state = state;
        if (text) text.textContent = STATUS_LABELS[state] || STATUS_LABELS.stopped;
        if (button) {
            button.setAttribute('aria-label', `${button.dataset.label || button.textContent.trim()}，${STATUS_LABELS[state] || STATUS_LABELS.stopped}`);
        }
    }

    function syncAllWorkflowStatuses() {
        WORKFLOW_APPS.forEach(syncWorkflowStatus);
    }

    function syncTabs() {
        const tabs = Array.from(document.querySelectorAll('.app-button'));
        tabs.forEach((tab) => {
            const selected = tab.classList.contains('active');
            tab.setAttribute('role', 'tab');
            tab.setAttribute('aria-selected', String(selected));
            tab.tabIndex = selected ? 0 : -1;
        });
    }

    function setupTabKeyboardNavigation() {
        const tablist = document.querySelector('.app-switcher');
        if (!tablist) return;
        tablist.setAttribute('role', 'tablist');
        tablist.setAttribute('aria-label', '研究引擎与报告视图');

        tablist.addEventListener('keydown', (event) => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) return;

            const tabs = Array.from(tablist.querySelectorAll('.app-button:not(.locked)'));
            const currentIndex = tabs.indexOf(document.activeElement);
            if (currentIndex < 0) return;

            event.preventDefault();
            let nextIndex = currentIndex;
            if (event.key === 'ArrowLeft') nextIndex = (currentIndex - 1 + tabs.length) % tabs.length;
            if (event.key === 'ArrowRight') nextIndex = (currentIndex + 1) % tabs.length;
            if (event.key === 'Home') nextIndex = 0;
            if (event.key === 'End') nextIndex = tabs.length - 1;

            tabs[nextIndex].focus();
            tabs[nextIndex].click();
        });
    }

    function setupQuickReportButton() {
        const quickReportButton = document.getElementById('quickReportButton');
        if (!quickReportButton) return;

        quickReportButton.addEventListener('click', () => {
            const reportTab = document.querySelector('.app-button[data-app="report"]');
            if (!reportTab) return;
            if (reportTab.classList.contains('locked')) {
                if (typeof window.showMessage === 'function') {
                    window.showMessage('报告入口将在洞察、媒体与检索任务完成后开放', 'info');
                }
                return;
            }
            reportTab.click();
            document.getElementById('embeddedHeader')?.scrollIntoView({ block: 'nearest' });
        });
    }

    function setupSearchState() {
        const searchButton = document.getElementById('searchButton');
        const searchInput = document.getElementById('searchInput');
        if (!searchButton || !searchInput) return;

        searchInput.setAttribute('aria-describedby', 'searchHint');
        const observer = new MutationObserver(() => {
            searchButton.setAttribute('aria-busy', String(searchButton.disabled));
        });
        observer.observe(searchButton, { attributes: true, attributeFilter: ['disabled'] });
        searchButton.setAttribute('aria-busy', String(searchButton.disabled));
    }

    function setupStatusObservers() {
        WORKFLOW_APPS.forEach((app) => {
            const indicator = document.getElementById(`status-${app}`);
            if (!indicator) return;
            new MutationObserver(() => syncWorkflowStatus(app)).observe(indicator, {
                attributes: true,
                attributeFilter: ['class']
            });
        });

        const tablist = document.querySelector('.app-switcher');
        if (tablist) {
            new MutationObserver(syncTabs).observe(tablist, {
                subtree: true,
                attributes: true,
                attributeFilter: ['class']
            });
        }
    }

    function setupConnectionStatus() {
        const connection = document.getElementById('connectionStatus');
        if (!connection) return;
        const sync = () => {
            const offline = connection.textContent.includes('断开');
            connection.dataset.state = offline ? 'offline' : 'online';
        };
        sync();
        new MutationObserver(sync).observe(connection, {
            childList: true,
            characterData: true,
            subtree: true
        });
    }

    function setupModalFocus(modal, closeSelector, triggerSelector) {
        if (!modal) return;
        const isVisible = () => modal.classList.contains('visible');
        let wasVisible = isVisible();
        let returnTarget = null;

        const trigger = triggerSelector ? document.querySelector(triggerSelector) : null;
        if (trigger) {
            trigger.addEventListener('click', () => {
                returnTarget = trigger;
                modalReturnFocus.set(modal, trigger);
            }, { capture: true });
        }

        new MutationObserver(() => {
            const visible = isVisible();
            if (visible && !wasVisible) {
                const activeElement = document.activeElement;
                if (!returnTarget && activeElement && !modal.contains(activeElement)) {
                    returnTarget = activeElement;
                    modalReturnFocus.set(modal, activeElement);
                }
                window.requestAnimationFrame(() => {
                    modal.querySelector(closeSelector)?.focus();
                });
            } else if (!visible && wasVisible) {
                const target = modalReturnFocus.get(modal) || returnTarget;
                if (target && typeof target.focus === 'function') target.focus();
                returnTarget = null;
            }
            wasVisible = visible;
        }).observe(modal, { attributes: true, attributeFilter: ['class'] });
    }

    function setupModalSemantics() {
        const configModal = document.getElementById('configModal');
        const shutdownModal = document.getElementById('shutdownConfirmModal');
        setupModalFocus(configModal, '#closeConfigModal', '#openConfigButton');
        setupModalFocus(shutdownModal, '#closeShutdownConfirm', '#shutdownButton');
    }

    ready(() => {
        syncTabs();
        syncAllWorkflowStatuses();
        setupTabKeyboardNavigation();
        setupQuickReportButton();
        setupSearchState();
        setupStatusObservers();
        setupConnectionStatus();
        setupModalSemantics();
    });
})();
