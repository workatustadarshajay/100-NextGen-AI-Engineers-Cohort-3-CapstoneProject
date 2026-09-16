(() => {
    const viewableStatuses = new Set(["workflowcompleted", "hitlcompleted"]);
    const statusLabels = {
        summarising: "Summarising",
        workflowcompleted: "Workflow completed",
        hitlcompleted: "HITL completed",
        failed: "Needs attention",
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
                window.location.assign(`/documents?new=${payload.document.id}`);
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
            body.innerHTML = `<tr><td colspan="4" class="px-6 py-16 text-center text-sm text-slate-500">No documents have entered the workflow yet.</td></tr>`;
            return;
        }

        body.innerHTML = documents.map((documentItem) => {
            const isOpenable = viewableStatuses.has(documentItem.status);
            const retryMarkup = documentItem.status === "failed"
                ? `<button type="button" class="inline-flex h-9 w-9 items-center justify-center rounded-lg text-slate-400 transition hover:bg-amber-50 hover:text-amber-700 focus:outline-none focus:ring-2 focus:ring-amber-200" data-retry-document="${documentItem.id}" data-file-name="${escapeHtml(documentItem.file_name)}" aria-label="Retry ${escapeHtml(documentItem.file_name)}" title="Retry processing"><i data-lucide="refresh-cw" class="h-4 w-4"></i></button>`
                : "";
            return `
                <tr class="table-row ${isOpenable ? "is-openable" : ""}" data-document-id="${documentItem.id}" data-openable="${isOpenable}" tabindex="${isOpenable ? "0" : "-1"}">
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
                const processing = items.some((item) => item.status === "summarising");
                if (processing) {
                    window.setTimeout(() => refreshDocuments(currentPage), 1800);
                }
            } catch (error) {
                setNotice(notice, error.message, "error");
            }
        };

        document.querySelector("#document-table-body")?.addEventListener("click", async (event) => {
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
        document.querySelector("#document-table-body")?.addEventListener("keydown", (event) => {
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
            refreshIcons();
        };

        saveButton?.addEventListener("click", async () => {
            setBusy(saveButton, true, "Saving edit");
            notice.hidden = true;
            try {
                const response = await fetch(`/api/edit/${documentId}`, {
                    method: "PATCH",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ summary: editor.value }),
                });
                const payload = await response.json();
                if (!response.ok) {
                    throw new Error(payload.detail || "Could not save the edit");
                }
                setDetailState(payload);
                setNotice(notice, "Your review edit is saved to the database.", "success");
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

    document.addEventListener("DOMContentLoaded", () => {
        refreshIcons();
        initUploadPage();
        initDocumentsPage();
        initDetailPage();
    });
})();
