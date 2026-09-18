(() => {
    const viewableStatuses = new Set(["workflowcompleted", "hitlcompleted"]);
    const statusLabels = {
        summarising: "Summarising",
        workflowcompleted: "Workflow completed",
        hitlcompleted: "HITL completed",
        failed: "Needs attention",
    };
    const workflowStageLabels = {
        starting: "Queued for processing",
        analyze_report: "Extracting report context",
        retrieve_guidelines: "Retrieving guideline references",
        route_review: "Routing clinical review",
        prepare_urgent_review: "Prioritising urgent review",
        prepare_standard_review: "Preparing standard review",
        summarise: "Writing clinician summary",
        recommend: "Preparing follow-up recommendations",
        completed: "Ready for human review",
        failed: "Workflow stopped",
    };
    const workflowStageProgress = {
        starting: 8,
        analyze_report: 22,
        retrieve_guidelines: 45,
        route_review: 60,
        prepare_urgent_review: 68,
        prepare_standard_review: 68,
        summarise: 82,
        recommend: 94,
        completed: 100,
        failed: 100,
    };

    const escapeHtml = (value) => String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");

    const statusLabel = (status) => statusLabels[status] || status;

    const statusMarkup = (status) => (
        `<span class="status-pill status-${escapeHtml(status)}">${escapeHtml(statusLabel(status))}</span>`
    );

    const formatDate = (value) => {
        if (!value) {
            return "-";
        }
        return new Intl.DateTimeFormat("en", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit",
        }).format(new Date(value));
    };

    const refreshIcons = () => {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    };

    const setNotice = (element, message, type = "") => {
        if (!element) {
            return;
        }
        element.className = `notice ${type ? `is-${type}` : ""}`;
        element.innerHTML = `<i data-lucide="info" class="mt-0.5 h-4 w-4 shrink-0"></i><span>${escapeHtml(message)}</span>`;
        element.hidden = false;
        refreshIcons();
    };

    const setBusy = (button, busy, busyLabel) => {
        if (!button) {
            return;
        }
        if (busy) {
            button.dataset.originalLabel = button.textContent.trim();
            button.disabled = true;
            button.innerHTML = `<i data-lucide="loader-circle" class="h-4 w-4 animate-spin"></i><span>${busyLabel}</span>`;
        } else {
            button.disabled = false;
            button.textContent = button.dataset.originalLabel || button.textContent;
        }
        refreshIcons();
    };

    const initDashboard = () => {
        const page = document.querySelector("[data-page=dashboard]");
        if (!page) {
            return;
        }

        const notice = page.querySelector("[data-dashboard-notice]");
        const monitorBody = page.querySelector("[data-workflow-monitor-body]");
        const liveCount = page.querySelector("[data-workflow-live-count]");
        const newDocumentId = new URLSearchParams(window.location.search).get("new");
        let refreshTimer;

        if (newDocumentId) {
            setNotice(notice, "Your PDF is queued. Agent progress will appear below while it is processed.", "success");
        }

        const renderMonitor = (items) => {
            const processingItems = items.filter((item) => item.status === "summarising");
            if (liveCount) {
                liveCount.textContent = processingItems.length;
            }
            if (!monitorBody) {
                return;
            }
            if (!items.length) {
                monitorBody.innerHTML = '<div class="rounded-xl border border-dashed border-slate-200 px-4 py-8 text-center text-sm text-slate-500">No workflow activity yet.</div>';
                return;
            }
            monitorBody.innerHTML = items.map((item) => {
                const stage = item.workflow_stage || (item.status === "summarising" ? "starting" : "completed");
                const stageLabel = workflowStageLabels[stage] || stage.replaceAll("_", " ");
                const progress = workflowStageProgress[stage] || (item.status === "failed" ? 100 : 12);
                const progressColor = item.status === "failed" ? "bg-coral" : "bg-signal";
                const eventLabel = item.last_event?.event
                    ? item.last_event.event.replaceAll("_", " ")
                    : "queued";
                const errorMarkup = item.error_message
                    ? `<p class="mt-3 rounded-lg bg-rose-50 px-3 py-2 text-xs leading-5 text-rose-700">${escapeHtml(item.error_message)}</p>`
                    : "";
                return `
                    <article class="rounded-xl border border-slate-100 bg-slate-50/70 px-4 py-4" data-workflow-id="${item.id}">
                        <div class="flex flex-col justify-between gap-3 sm:flex-row sm:items-start">
                            <div class="min-w-0">
                                <p class="truncate text-sm font-semibold text-ink">${escapeHtml(item.file_name)}</p>
                                <p class="mt-1 text-xs font-semibold text-slate-500">${escapeHtml(stageLabel)}</p>
                            </div>
                            <div class="flex shrink-0 items-center gap-2">
                                ${statusMarkup(item.status)}
                                <span class="text-[11px] font-semibold text-slate-400">Attempt ${escapeHtml(item.workflow_attempts || 0)}</span>
                            </div>
                        </div>
                        <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-slate-200">
                            <div class="h-full rounded-full ${progressColor} transition-[width] duration-500" style="width: ${progress}%"></div>
                        </div>
                        <div class="mt-2 flex flex-wrap justify-between gap-2 text-[11px] font-semibold text-slate-400">
                            <span>Last event: ${escapeHtml(eventLabel)}</span>
                            <span>${escapeHtml(formatDate(item.modified))}</span>
                        </div>
                        ${errorMarkup}
                    </article>
                `;
            }).join("");
            refreshIcons();
        };

        const refreshDashboard = async () => {
            try {
                const response = await fetch("/api/dashboard", { headers: { Accept: "application/json" } });
                if (!response.ok) {
                    throw new Error("The workflow monitor is temporarily unavailable.");
                }
                const payload = await response.json();
                const values = {
                    processed_today: payload.processed_today,
                    average_processing_minutes: payload.average_processing_minutes,
                    pending_reviews: payload.pending_reviews,
                    failed_workflows: payload.failed_workflows,
                };
                Object.entries(values).forEach(([key, value]) => {
                    const target = page.querySelector(`[data-dashboard-stat=${key}]`);
                    if (!target) {
                        return;
                    }
                    if (key === "average_processing_minutes") {
                        target.innerHTML = `${escapeHtml(value)}<span class="ml-1 text-sm font-semibold tracking-normal text-slate-400">min</span>`;
                    } else {
                        target.textContent = value;
                    }
                });
                const items = payload.workflow_monitor || [];
                renderMonitor(items);
                const hasProcessing = items.some((item) => item.status === "summarising");
                window.clearTimeout(refreshTimer);
                refreshTimer = window.setTimeout(refreshDashboard, hasProcessing ? 1800 : 10000);
            } catch (error) {
                setNotice(notice, error.message, "error");
                window.clearTimeout(refreshTimer);
                refreshTimer = window.setTimeout(refreshDashboard, 5000);
            }
        };

        refreshDashboard();
    };

    const initUploadPage = () => {
        const form = document.querySelector("#upload-form");
        if (!form) {
            return;
        }

        const fileInput = form.querySelector("#pdf-file");
        const dropzone = form.querySelector("#upload-dropzone");
        const selectedFile = form.querySelector("#selected-file");
        const submitButton = form.querySelector("button[type=submit]");
        const notice = form.querySelector("[data-upload-notice]");

        const updateSelectedFile = () => {
            const file = fileInput.files[0];
            if (!file) {
                selectedFile.hidden = true;
                selectedFile.textContent = "";
                return;
            }
            selectedFile.hidden = false;
            selectedFile.textContent = `${file.name} - ${(file.size / 1024 / 1024).toFixed(2)} MB`;
        };

        fileInput.addEventListener("change", updateSelectedFile);
        ["dragenter", "dragover"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.add("is-dragging");
            });
        });
        ["dragleave", "drop"].forEach((eventName) => {
            dropzone.addEventListener(eventName, (event) => {
                event.preventDefault();
                dropzone.classList.remove("is-dragging");
            });
        });
        dropzone.addEventListener("drop", (event) => {
            const [file] = event.dataTransfer.files;
            if (!file) {
                return;
            }
            const transfer = new DataTransfer();
            transfer.items.add(file);
            fileInput.files = transfer.files;
            updateSelectedFile();
        });

        form.addEventListener("submit", async (event) => {
            event.preventDefault();
            const file = fileInput.files[0];
            if (!file) {
                setNotice(notice, "Choose a PDF before uploading.", "error");
                return;
            }
            if (!file.name.toLowerCase().endsWith(".pdf")) {
                setNotice(notice, "Only PDF files are accepted.", "error");
                return;
            }

            setBusy(submitButton, true, "Queueing file");
            notice.hidden = true;
            try {
                const response = await fetch("/api/upload", {
                    method: "POST",
                    body: new FormData(form),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || "Upload failed");
                }
                window.location.assign(`/dashboard?new=${payload.document.id}`);
            } catch (error) {
                setNotice(notice, error.message, "error");
                setBusy(submitButton, false);
            }
        });
    };

    const renderDocumentRows = (documents) => {
        const body = document.querySelector("#document-table-body");
        if (!body) {
            return;
        }
        if (!documents.length) {
            body.innerHTML = `<tr><td colspan="5" class="px-6 py-16 text-center text-sm text-slate-500">No documents have entered the workflow yet.</td></tr>`;
            return;
        }

        body.innerHTML = documents.map((documentItem) => {
            const isOpenable = viewableStatuses.has(documentItem.status);
            const retryMarkup = documentItem.status === "failed"
                ? `<button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-amber-50 hover:text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-200" data-retry-document="${documentItem.id}" data-file-name="${escapeHtml(documentItem.file_name)}" aria-label="Retry ${escapeHtml(documentItem.file_name)}" title="Retry processing"><i data-lucide="refresh-cw" class="h-4 w-4"></i></button>`
                : "";
            return `
                <tr class="table-row ${isOpenable ? "is-openable" : ""}" data-document-id="${documentItem.id}" data-openable="${isOpenable}" tabindex="${isOpenable ? "0" : "-1"}">
                    <td class="w-12 px-4 py-4 sm:px-6"><input type="checkbox" data-document-select value="${documentItem.id}" class="h-4 w-4 rounded border-slate-300 text-signal focus:ring-cyan-200" aria-label="Select ${escapeHtml(documentItem.file_name)}"></td>
                    <td class="px-4 py-4 sm:px-6">
                        <div class="flex min-w-0 items-center justify-between gap-4">
                            <div class="flex min-w-0 items-center gap-3">
                                <span class="file-icon shrink-0"><i data-lucide="file-text" class="h-4 w-4"></i></span>
                                <span class="min-w-0">
                                    <span class="block truncate font-semibold text-slate-800">${escapeHtml(documentItem.file_name)}</span>
                                    <span class="mt-1 block text-xs text-slate-400">PDF document</span>
                                </span>
                            </div>
                            <div class="flex shrink-0 items-center gap-1">
                                ${retryMarkup}
                                <button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-rose-50 hover:text-rose-600 focus:outline-none focus:ring-2 focus:ring-rose-200" data-delete-document="${documentItem.id}" data-file-name="${escapeHtml(documentItem.file_name)}" aria-label="Delete ${escapeHtml(documentItem.file_name)}" title="Delete PDF">
                                    <i data-lucide="trash-2" class="h-4 w-4"></i>
                                </button>
                            </div>
                        </div>
                    </td>
                    <td class="px-4 py-4 sm:px-6">${statusMarkup(documentItem.status)}</td>
                    <td class="whitespace-nowrap px-4 py-4 text-sm text-slate-600 sm:px-6">${escapeHtml(formatDate(documentItem.date_received))}</td>
                    <td class="whitespace-nowrap px-4 py-4 text-sm text-slate-600 sm:px-6">${escapeHtml(formatDate(documentItem.modified))}</td>
                </tr>
            `;
        }).join("");
        refreshIcons();
    };

    const initDocumentsPage = () => {
        const page = document.querySelector("[data-page=documents]");
        if (!page) {
            return;
        }

        const notice = document.querySelector("[data-documents-notice]");
        const pagination = document.querySelector("[data-pagination]");
        const previousPageButton = pagination?.querySelector("[data-page-action=previous]");
        const nextPageButton = pagination?.querySelector("[data-page-action=next]");
        const paginationLabel = pagination?.querySelector("[data-pagination-label]");
        const tableBody = page.querySelector("#document-table-body");
        const selectAll = page.querySelector("[data-select-all]");
        const bulkToolbar = page.querySelector("[data-bulk-toolbar]");
        const selectedCount = page.querySelector("[data-selected-count]");
        const bulkAssignee = page.querySelector("[data-bulk-assignee]");
        const bulkActionButtons = [...page.querySelectorAll("[data-bulk-action]")];
        const filterForm = page.querySelector("[data-inbox-filters]");
        const searchInput = filterForm?.querySelector("[name=search]");
        const statusSelect = filterForm?.querySelector("[name=status]");
        const queryParams = new URLSearchParams(window.location.search);
        const newDocumentId = queryParams.get("new");
        const requestedPage = Number.parseInt(queryParams.get("page") || "1", 10);
        const pageSize = 5;
        let currentPage = Number.isInteger(requestedPage) && requestedPage > 0 ? requestedPage : 1;
        let filters = {
            search: (queryParams.get("search") || "").trim(),
            status: queryParams.get("status") || "",
        };
        if (searchInput) {
            searchInput.value = filters.search;
        }
        if (statusSelect) {
            statusSelect.value = filters.status;
        }
        if (newDocumentId) {
            setNotice(notice, "Your PDF is in the queue. This inbox will update when the workflow finishes.", "success");
        }
        if (new URLSearchParams(window.location.search).get("notice") === "locked") {
            setNotice(notice, "That document is still processing and cannot be opened yet.", "");
        }

        const getSelectedIds = () => [...page.querySelectorAll("[data-document-select]:checked")]
            .map((checkbox) => Number.parseInt(checkbox.value, 10))
            .filter((documentId) => Number.isInteger(documentId));

        const updateBulkToolbar = () => {
            const selectedIds = getSelectedIds();
            const hasSelection = selectedIds.length > 0;
            bulkToolbar?.classList.toggle("hidden", !hasSelection);
            bulkToolbar?.classList.toggle("flex", hasSelection);
            if (selectedCount) {
                selectedCount.textContent = selectedIds.length;
            }
            bulkActionButtons.forEach((button) => {
                button.disabled = !hasSelection || (button.dataset.bulkAction === "assign" && !bulkAssignee?.value);
            });
            if (selectAll) {
                const checkboxes = [...page.querySelectorAll("[data-document-select]")];
                selectAll.checked = checkboxes.length > 0 && checkboxes.every((checkbox) => checkbox.checked);
                selectAll.indeterminate = hasSelection && !selectAll.checked;
            }
        };

        const resetBulkSelection = () => {
            page.querySelectorAll("[data-document-select]").forEach((checkbox) => {
                checkbox.checked = false;
            });
            if (selectAll) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
            if (bulkAssignee) {
                bulkAssignee.value = "";
            }
            updateBulkToolbar();
        };

        const refreshStats = (documents, payload) => {
            const counts = payload.counts || documents.reduce((result, item) => {
                result[item.status] = (result[item.status] || 0) + 1;
                return result;
            }, {});
            const values = {
                total: payload.total ?? documents.length,
                processing: counts.summarising || 0,
                review: counts.workflowcompleted || 0,
                signed: counts.hitlcompleted || 0,
            };
            Object.entries(values).forEach(([key, value]) => {
                const target = document.querySelector(`[data-stat=${key}]`);
                if (target) {
                    target.textContent = value;
                }
            });
        };

        const renderPagination = (payload) => {
            if (!pagination || !paginationLabel || !previousPageButton || !nextPageButton) {
                return;
            }
            const totalPages = Math.max(1, Number(payload.total_pages) || 1);
            currentPage = Number(payload.page) || 1;
            pagination.hidden = totalPages <= 1;
            paginationLabel.textContent = `Page ${currentPage} of ${totalPages}`;
            previousPageButton.disabled = currentPage <= 1;
            nextPageButton.disabled = currentPage >= totalPages;
            const url = new URL(window.location.href);
            if (currentPage > 1) {
                url.searchParams.set("page", currentPage);
            } else {
                url.searchParams.delete("page");
            }
            window.history.replaceState({}, "", url);
            refreshIcons();
        };

        const highlightNewRow = () => {
            if (!newDocumentId) {
                return;
            }
            const row = document.querySelector(`[data-document-id="${newDocumentId}"]`);
            if (row) {
                row.classList.add("is-new");
            }
        };

        const refreshDocuments = async (requestedPage = currentPage) => {
            try {
                const params = new URLSearchParams({ page: requestedPage, page_size: pageSize });
                if (filters.search) {
                    params.set("search", filters.search);
                }
                if (filters.status) {
                    params.set("status", filters.status);
                }
                const response = await fetch(`/api/display?${params}`, { headers: { Accept: "application/json" } });
                if (!response.ok) {
                    let detail = "";
                    try {
                        const errorPayload = await response.json();
                        detail = errorPayload.detail || "";
                    } catch {
                        detail = "";
                    }
                    throw new Error(detail || "The document inbox is temporarily unavailable.");
                }
                const documents = await response.json();
                const items = Array.isArray(documents) ? documents : documents.items;
                if (!Array.isArray(documents) && requestedPage > documents.total_pages && documents.total_pages > 0) {
                    return refreshDocuments(documents.total_pages);
                }
                renderDocumentRows(items);
                refreshStats(items, Array.isArray(documents) ? {} : documents);
                if (!Array.isArray(documents)) {
                    renderPagination(documents);
                }
                highlightNewRow();
                updateBulkToolbar();
                const processing = items.some((item) => item.status === "summarising");
                if (processing) {
                    window.setTimeout(() => refreshDocuments(currentPage), 1800);
                }
            } catch (error) {
                setNotice(notice, error.message, "error");
            }
        };

        const performBulkAction = async (action) => {
            const documentIds = getSelectedIds();
            if (!documentIds.length) {
                return;
            }
            if (action === "assign" && !bulkAssignee?.value) {
                setNotice(notice, "Choose a reviewer before assigning documents.", "error");
                return;
            }
            if (action === "delete" && !window.confirm(`Delete ${documentIds.length} selected document${documentIds.length === 1 ? "" : "s"}? This action cannot be undone.`)) {
                return;
            }

            bulkActionButtons.forEach((button) => {
                button.disabled = true;
            });
            try {
                const payload = { document_ids: documentIds, action };
                if (action === "assign") {
                    payload.assignee_id = Number.parseInt(bulkAssignee.value, 10);
                }
                const endpoint = action === "export" ? "/api/documents/export" : "/api/documents/bulk";
                const response = await fetch(endpoint, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Accept: "application/json" },
                    body: JSON.stringify(action === "export" ? { document_ids: documentIds } : payload),
                });
                if (!response.ok) {
                    let detail = "Bulk action failed";
                    try {
                        const errorPayload = await response.json();
                        detail = errorPayload.detail || detail;
                    } catch {
                        detail = "Bulk action failed";
                    }
                    throw new Error(detail);
                }
                if (action === "export") {
                    const downloadUrl = URL.createObjectURL(await response.blob());
                    const link = document.createElement("a");
                    link.href = downloadUrl;
                    link.download = "neuron-document-export.csv";
                    document.body.appendChild(link);
                    link.click();
                    link.remove();
                    URL.revokeObjectURL(downloadUrl);
                    setNotice(notice, "The selected records were exported.", "success");
                } else {
                    const result = await response.json();
                    setNotice(notice, `${result.message} ${result.skipped_count ? `${result.skipped_count} skipped.` : ""}`.trim(), "success");
                    resetBulkSelection();
                    await refreshDocuments(currentPage);
                }
            } catch (error) {
                setNotice(notice, error.message, "error");
            } finally {
                updateBulkToolbar();
            }
        };

        tableBody?.addEventListener("change", (event) => {
            if (event.target.matches("[data-document-select]")) {
                updateBulkToolbar();
            }
        });
        selectAll?.addEventListener("change", () => {
            page.querySelectorAll("[data-document-select]").forEach((checkbox) => {
                checkbox.checked = selectAll.checked;
            });
            updateBulkToolbar();
        });
        bulkAssignee?.addEventListener("change", updateBulkToolbar);
        bulkActionButtons.forEach((button) => {
            button.addEventListener("click", () => performBulkAction(button.dataset.bulkAction));
        });

        tableBody?.addEventListener("click", async (event) => {
            if (event.target.closest("[data-document-select]")) {
                event.stopPropagation();
                return;
            }
            const retryButton = event.target.closest("[data-retry-document]");
            if (retryButton) {
                event.preventDefault();
                event.stopPropagation();
                const originalMarkup = retryButton.innerHTML;
                retryButton.disabled = true;
                retryButton.innerHTML = '<i data-lucide="loader-circle" class="h-4 w-4 animate-spin"></i>';
                refreshIcons();
                try {
                    const response = await fetch(`/api/summarise/${retryButton.dataset.retryDocument}`, { method: "POST" });
                    const payload = await response.json();
                    if (!response.ok) {
                        throw new Error(payload.detail || "Could not retry the document");
                    }
                    setNotice(notice, "The document has been queued for processing again.", "success");
                    await refreshDocuments(currentPage);
                } catch (error) {
                    retryButton.disabled = false;
                    retryButton.innerHTML = originalMarkup;
                    setNotice(notice, error.message, "error");
                    refreshIcons();
                }
                return;
            }
            const deleteButton = event.target.closest("[data-delete-document]");
            if (deleteButton) {
                event.preventDefault();
                event.stopPropagation();
                const fileName = deleteButton.dataset.fileName || "this PDF";
                if (!window.confirm(`Delete ${fileName}? This action cannot be undone.`)) {
                    return;
                }
                deleteButton.disabled = true;
                try {
                    const response = await fetch(`/api/documents/${deleteButton.dataset.deleteDocument}`, { method: "DELETE" });
                    const payload = await response.json();
                    if (!response.ok) {
                        throw new Error(payload.detail || "Could not delete the document");
                    }
                    setNotice(notice, "The PDF and its document record were deleted.", "success");
                    await refreshDocuments(currentPage);
                } catch (error) {
                    deleteButton.disabled = false;
                    setNotice(notice, error.message, "error");
                }
                return;
            }
            const row = event.target.closest("tr[data-document-id]");
            if (row?.dataset.openable === "true") {
                window.location.assign(`/documents/${row.dataset.documentId}`);
            }
        });
        tableBody?.addEventListener("keydown", (event) => {
            if (event.target.closest("[data-document-select]")) {
                return;
            }
            if (event.target.closest("[data-delete-document]")) {
                return;
            }
            const row = event.target.closest("tr[data-document-id]");
            if (row?.dataset.openable === "true" && (event.key === "Enter" || event.key === " ")) {
                event.preventDefault();
                window.location.assign(`/documents/${row.dataset.documentId}`);
            }
        });

        pagination?.addEventListener("click", (event) => {
            const button = event.target.closest("[data-page-action]");
            if (!button || button.disabled) {
                return;
            }
            const nextPage = button.dataset.pageAction === "next" ? currentPage + 1 : currentPage - 1;
            if (nextPage >= 1) {
                refreshDocuments(nextPage);
            }
        });

        filterForm?.addEventListener("submit", (event) => {
            event.preventDefault();
            filters = {
                search: searchInput?.value.trim() || "",
                status: statusSelect?.value || "",
            };
            const url = new URL(window.location.href);
            url.searchParams.delete("page");
            if (filters.search) {
                url.searchParams.set("search", filters.search);
            } else {
                url.searchParams.delete("search");
            }
            if (filters.status) {
                url.searchParams.set("status", filters.status);
            } else {
                url.searchParams.delete("status");
            }
            window.history.pushState({}, "", url);
            refreshDocuments(1);
        });

        refreshDocuments();
    };

    const initDetailPage = () => {
        const page = document.querySelector("[data-page=detail]");
        if (!page) {
            return;
        }

        const pdfViewers = [...page.querySelectorAll("[data-pdf-viewer]")];
        const pdfModal = page.querySelector("#pdf-modal");
        const openPdfModalButton = page.querySelector("#open-pdf-modal");
        const closePdfModalButton = page.querySelector("#close-pdf-modal");
        const pdfModalBackdrop = page.querySelector("[data-pdf-modal-backdrop]");
        let currentPdfPage = 1;
        let lastFocusedElement = null;

        const setPdfPage = (requestedPage) => {
            if (!pdfViewers.length) {
                return;
            }
            const parsedPage = Number.parseInt(requestedPage, 10);
            currentPdfPage = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1;
            pdfViewers.forEach((viewer) => {
                const pdfPreview = viewer.querySelector("iframe[data-pdf-url]");
                const pdfPageInput = viewer.querySelector("[data-pdf-page]");
                const previousPdfPage = viewer.querySelector("[data-pdf-page-action=previous]");
                if (pdfPageInput) {
                    pdfPageInput.value = currentPdfPage;
                }
                if (pdfPreview) {
                    pdfPreview.src = `${pdfPreview.dataset.pdfUrl}#page=${currentPdfPage}`;
                }
                if (previousPdfPage) {
                    previousPdfPage.disabled = currentPdfPage <= 1;
                }
            });
        };

        pdfViewers.forEach((viewer) => {
            const previousPdfPage = viewer.querySelector("[data-pdf-page-action=previous]");
            const nextPdfPage = viewer.querySelector("[data-pdf-page-action=next]");
            const pdfPageInput = viewer.querySelector("[data-pdf-page]");
            previousPdfPage?.addEventListener("click", () => setPdfPage(currentPdfPage - 1));
            nextPdfPage?.addEventListener("click", () => setPdfPage(currentPdfPage + 1));
            pdfPageInput?.addEventListener("change", () => setPdfPage(pdfPageInput.value));
            pdfPageInput?.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    setPdfPage(pdfPageInput.value);
                }
            });
        });

        const closePdfModal = () => {
            if (!pdfModal) {
                return;
            }
            pdfModal.classList.add("hidden");
            pdfModal.setAttribute("aria-hidden", "true");
            document.body.classList.remove("overflow-hidden");
            lastFocusedElement?.focus();
        };

        const openPdfModal = () => {
            if (!pdfModal) {
                return;
            }
            lastFocusedElement = document.activeElement;
            pdfModal.classList.remove("hidden");
            pdfModal.setAttribute("aria-hidden", "false");
            document.body.classList.add("overflow-hidden");
            setPdfPage(currentPdfPage);
            closePdfModalButton?.focus();
        };

        openPdfModalButton?.addEventListener("click", openPdfModal);
        closePdfModalButton?.addEventListener("click", closePdfModal);
        pdfModalBackdrop?.addEventListener("click", closePdfModal);
        page.addEventListener("click", (event) => {
            const evidenceButton = event.target.closest("[data-evidence-page]");
            if (!evidenceButton) {
                return;
            }
            event.preventDefault();
            setPdfPage(evidenceButton.dataset.evidencePage);
            if (window.matchMedia("(max-width: 1023px)").matches) {
                openPdfModal();
                return;
            }
            page.querySelector("#pdf-preview")?.closest("[data-pdf-viewer]")?.scrollIntoView({
                behavior: "smooth",
                block: "start",
            });
        });
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && pdfModal && !pdfModal.classList.contains("hidden")) {
                closePdfModal();
            }
        });

        const documentId = page.dataset.documentId;
        const editor = page.querySelector("#summary-editor");
        const saveButton = page.querySelector("#save-edit");
        const submitButton = page.querySelector("#submit-document");
        const notice = page.querySelector("[data-detail-notice]");
        const statusTargets = page.querySelectorAll("[data-detail-status]");
        const lockedMessage = page.querySelector("#locked-message");
        const modeLabel = page.querySelector("#detail-mode-label");
        const helperCopy = page.querySelector("#detail-helper-copy");
        const correctionReason = page.querySelector("#edit-feedback-reason");
        const recommendationItems = [...page.querySelectorAll("[data-recommendation-item]")];
        let feedbackEditable = editor ? !editor.readOnly : false;

        const feedbackDecisionLabel = (decision) => ({
            accepted: "Accepted",
            rejected: "Rejected",
        }[decision] || "Not reviewed");

        const setFeedbackError = (item, message = "") => {
            const error = item.querySelector("[data-feedback-error]");
            if (!error) {
                return;
            }
            error.textContent = message;
            error.hidden = !message;
        };

        const setRecommendationFeedback = (item, decision) => {
            item.dataset.feedbackDecision = decision;
            item.querySelectorAll("[data-feedback-action]").forEach((button) => {
                const action = button.dataset.feedbackAction;
                const selected = action === decision;
                const label = button.querySelector("span");
                if (label) {
                    label.textContent = selected
                        ? (action === "accepted" ? "Accepted" : "Rejected")
                        : (action === "accepted" ? "Accept" : "Reject");
                }
                button.setAttribute("aria-pressed", String(selected));
                button.title = selected
                    ? `${action === "accepted" ? "Accepted" : "Rejected"} recommendation`
                    : `${action === "accepted" ? "Accept" : "Reject"} recommendation`;
            });
            const status = item.querySelector("[data-feedback-status]");
            if (status) {
                status.textContent = feedbackDecisionLabel(decision);
                status.className = "text-[11px] font-bold "
                    + (decision === "accepted"
                        ? "text-emerald-600"
                        : decision === "rejected" ? "text-rose-600" : "text-slate-400");
            }
            const reasonPanel = item.querySelector("[data-feedback-reason-panel]");
            const showReason = feedbackEditable && decision === "rejected";
            reasonPanel?.classList.toggle("hidden", !showReason);
            if (reasonPanel) {
                reasonPanel.hidden = !showReason;
            }
        };

        const setFeedbackEditable = (canEdit) => {
            feedbackEditable = canEdit;
            recommendationItems.forEach((item) => {
                const decision = item.dataset.feedbackDecision || "";
                item.querySelectorAll("[data-feedback-action], [data-feedback-submit-rejection]")
                    .forEach((button) => { button.disabled = !canEdit; });
                const reason = item.querySelector("[data-feedback-reason]");
                if (reason) {
                    reason.disabled = !canEdit;
                }
                setRecommendationFeedback(item, decision);
                if (!canEdit) {
                    setFeedbackError(item);
                }
            });
        };

        const submitRecommendationFeedback = async (item, decision, reason) => {
            if (!feedbackEditable) {
                return;
            }
            const recommendationIndex = item.dataset.recommendationIndex;
            const controls = [...item.querySelectorAll("[data-feedback-action], [data-feedback-submit-rejection]")];
            controls.forEach((button) => { button.disabled = true; });
            setFeedbackError(item);
            try {
                const response = await fetch(
                    `/api/documents/${documentId}/recommendations/${recommendationIndex}/feedback`,
                    {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ decision, reason: reason || null }),
                    },
                );
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    throw new Error(payload.detail || "Could not save recommendation feedback");
                }
                setRecommendationFeedback(item, payload.decision);
                setNotice(notice, payload.message, "success");
            } catch (error) {
                setNotice(notice, error.message, "error");
            } finally {
                controls.forEach((button) => { button.disabled = !feedbackEditable; });
            }
        };

        recommendationItems.forEach((item) => {
            const acceptButton = item.querySelector('[data-feedback-action="accepted"]');
            const rejectButton = item.querySelector('[data-feedback-action="rejected"]');
            const saveRejectionButton = item.querySelector("[data-feedback-submit-rejection]");
            const reason = item.querySelector("[data-feedback-reason]");
            const showRejectionForm = () => {
                const panel = item.querySelector("[data-feedback-reason-panel]");
                panel?.classList.remove("hidden");
                if (panel) {
                    panel.hidden = false;
                }
                reason?.focus();
            };
            const rejectWithReason = () => {
                const value = reason?.value.trim() || "";
                if (!value) {
                    showRejectionForm();
                    setFeedbackError(item, "Add a reason before saving a rejection.");
                    return;
                }
                submitRecommendationFeedback(item, "rejected", value);
            };
            acceptButton?.addEventListener("click", () => {
                submitRecommendationFeedback(item, "accepted", "");
            });
            rejectButton?.addEventListener("click", rejectWithReason);
            saveRejectionButton?.addEventListener("click", rejectWithReason);
            reason?.addEventListener("input", () => setFeedbackError(item));
            setRecommendationFeedback(item, item.dataset.feedbackDecision || "");
        });
        setFeedbackEditable(feedbackEditable);

        if (new URLSearchParams(window.location.search).get("notice") === "reconciled") {
            setNotice(notice, "Your edit and dependent findings were synchronized.", "success");
        }

        const setDetailState = (payload) => {
            statusTargets.forEach((target) => {
                target.innerHTML = statusMarkup(payload.status);
            });
            if (payload.summary !== null && payload.summary !== undefined) {
                editor.value = payload.summary;
            }
            const canEdit = payload.can_edit;
            editor.readOnly = !canEdit;
            saveButton.hidden = !canEdit;
            submitButton.hidden = !canEdit;
            lockedMessage.hidden = canEdit;
            lockedMessage.classList.toggle("hidden", canEdit);
            modeLabel.textContent = canEdit ? "Editable" : "Read only";
            helperCopy.textContent = canEdit
                ? "Make any corrections before you submit the review."
                : "This summary is locked after human sign-off.";
            setFeedbackEditable(canEdit);
            refreshIcons();
        };

        saveButton?.addEventListener("click", async () => {
            setBusy(saveButton, true, "Synchronizing findings");
            notice.hidden = true;
            try {
                const response = await fetch(`/api/edit/${documentId}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        summary: editor.value,
                        feedback_reason: correctionReason?.value.trim() || null,
                    }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || "Could not save the edit");
                }
                window.location.assign(`/documents/${documentId}?notice=reconciled`);
            } catch (error) {
                setNotice(notice, error.message, "error");
            } finally {
                setBusy(saveButton, false);
            }
        });

        submitButton?.addEventListener("click", async () => {
            setBusy(submitButton, true, "Submitting review");
            notice.hidden = true;
            try {
                const response = await fetch(`/api/submit/${documentId}`, { method: "POST" });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || "Could not submit the document");
                }
                setDetailState(payload);
                setNotice(notice, "Review submitted. This document is now locked as HITL complete.", "success");
            } catch (error) {
                setNotice(notice, error.message, "error");
                setBusy(submitButton, false);
            }
        });
    };

    const initNotifications = () => {
        const root = document.querySelector("[data-notifications]");
        if (!root) {
            return;
        }
        const toggle = root.querySelector("[data-notifications-toggle]");
        const panel = root.querySelector("[data-notifications-panel]");
        const count = root.querySelector("[data-notification-count]");
        const list = root.querySelector("[data-notifications-list]");
        const readAll = root.querySelector("[data-notifications-read-all]");

        const renderNotifications = (payload) => {
            const notifications = payload.notifications || [];
            const unreadCount = Number(payload.unread_count) || 0;
            if (count) {
                count.textContent = unreadCount > 99 ? "99+" : unreadCount;
                count.classList.toggle("hidden", unreadCount === 0);
            }
            if (!list) {
                return;
            }
            if (!notifications.length) {
                list.innerHTML = '<div class="px-4 py-8 text-center text-xs font-semibold text-slate-400">No notifications yet.</div>';
                return;
            }
            list.innerHTML = notifications.map((notification) => `
                <button type="button" data-notification-id="${notification.id}" data-document-id="${notification.document_id || ""}" class="flex w-full items-start gap-3 border-b border-slate-100 px-4 py-3 text-left transition hover:bg-slate-50 ${notification.read_at ? "" : "bg-cyan-50/50"}">
                    <span class="mt-1 h-2 w-2 shrink-0 rounded-full ${notification.read_at ? "bg-slate-200" : "bg-signal"}"></span>
                    <span class="min-w-0">
                        <span class="block text-xs font-bold text-ink">${escapeHtml(notification.title)}</span>
                        <span class="mt-1 block text-xs leading-5 text-slate-500">${escapeHtml(notification.message)}</span>
                        <span class="mt-1 block text-[10px] font-semibold text-slate-400">${escapeHtml(formatDate(notification.created_at))}</span>
                    </span>
                </button>
            `).join("");
        };

        const loadNotifications = async () => {
            try {
                const response = await fetch("/api/notifications?limit=8", { headers: { Accept: "application/json" } });
                if (response.ok) {
                    renderNotifications(await response.json());
                }
            } catch {
                // Notifications should not interrupt the document workflow.
            }
        };

        toggle?.addEventListener("click", () => {
            const isHidden = panel?.classList.toggle("hidden");
            toggle.setAttribute("aria-expanded", String(isHidden === false));
            if (isHidden === false) {
                loadNotifications();
            }
        });
        readAll?.addEventListener("click", async () => {
            await fetch("/api/notifications/read-all", { method: "POST" });
            loadNotifications();
        });
        list?.addEventListener("click", async (event) => {
            const notification = event.target.closest("[data-notification-id]");
            if (!notification) {
                return;
            }
            await fetch(`/api/notifications/${notification.dataset.notificationId}/read`, { method: "POST" });
            const documentId = notification.dataset.documentId;
            if (documentId) {
                window.location.assign(`/documents/${documentId}`);
            } else {
                loadNotifications();
            }
        });
        document.addEventListener("click", (event) => {
            if (!root.contains(event.target) && panel && !panel.classList.contains("hidden")) {
                panel.classList.add("hidden");
                toggle?.setAttribute("aria-expanded", "false");
            }
        });
        loadNotifications();
        window.setInterval(loadNotifications, 30000);
    };

    const initProfileModal = () => {
        const toggle = document.querySelector("[data-profile-toggle]");
        const modal = document.querySelector("[data-profile-modal]");
        const closeButton = modal?.querySelector("[data-profile-close]");
        const backdrop = modal?.querySelector("[data-profile-backdrop]");
        let lastFocusedElement = null;

        const closeModal = () => {
            if (!modal) {
                return;
            }
            modal.classList.add("hidden");
            modal.setAttribute("aria-hidden", "true");
            toggle?.setAttribute("aria-expanded", "false");
            document.body.classList.remove("overflow-hidden");
            lastFocusedElement?.focus();
        };

        const openModal = () => {
            if (!modal) {
                return;
            }
            lastFocusedElement = document.activeElement;
            modal.classList.remove("hidden");
            modal.setAttribute("aria-hidden", "false");
            toggle?.setAttribute("aria-expanded", "true");
            document.body.classList.add("overflow-hidden");
            closeButton?.focus();
        };

        toggle?.addEventListener("click", openModal);
        closeButton?.addEventListener("click", closeModal);
        backdrop?.addEventListener("click", closeModal);
        document.addEventListener("keydown", (event) => {
            if (event.key === "Escape" && modal && !modal.classList.contains("hidden")) {
                closeModal();
            }
        });
    };

    document.addEventListener("DOMContentLoaded", () => {
        refreshIcons();
        initDashboard();
        initUploadPage();
        initDocumentsPage();
        initDetailPage();
        initNotifications();
        initProfileModal();
    });
})();
