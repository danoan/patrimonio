// Tab / segment toggles. Panels may live outside the [data-tab-group]
// element (e.g. inside an htmx-swapped container), so panel visibility is
// applied document-wide and re-run after every swap to survive refreshes.
function applyActiveTab() {
  const activeBtn = document.querySelector("[data-tab-group] [data-tab].active");
  if (!activeBtn) return;
  const target = activeBtn.dataset.tab;
  document.querySelectorAll("[data-panel]").forEach((p) => {
    p.hidden = p.dataset.panel !== target;
  });
}

document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-tab]");
  if (!btn) return;
  const group = btn.closest("[data-tab-group]");
  if (!group) return;
  group.querySelectorAll("[data-tab]").forEach((b) => b.classList.remove("active"));
  btn.classList.add("active");
  applyActiveTab();
});

document.body.addEventListener("htmx:afterSwap", applyActiveTab);

// Number mask: allow comma or dot as decimal separator, reformat on blur
document.addEventListener("blur", (e) => {
  const input = e.target;
  if (!input.classList?.contains("num-input")) return;
  const raw = input.value.replace(",", ".");
  const num = parseFloat(raw);
  if (!isNaN(num)) {
    input.value = num.toFixed(2).replace(".", ",");
  }
}, true);

// Recurring rule delete: confirm, then ask separately whether to also
// remove the lançamentos it already created. Runs in the capture phase so
// it settles before htmx's own (bubble-phase) click handler reads hx-delete.
document.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-delete-rule]");
  if (!btn) return;
  if (!confirm("Remover esta regra recorrente?")) {
    e.stopImmediatePropagation();
    return;
  }
  const alsoTxns = confirm("Remover também os lançamentos já criados por esta regra?");
  btn.setAttribute("hx-delete", `${btn.dataset.deleteUrl}?delete_txns=${alsoTxns}`);
}, true);

// Inline edit: Escape restores the cell's pre-edit text and marks the
// input as cancelled so the queued blur[...] htmx trigger does not save it.
document.addEventListener("keydown", (e) => {
  const input = e.target.closest("[data-editable-input]");
  if (!input || e.key !== "Escape") return;
  input.dataset.cancelled = "1";
  const cell = input.closest("td");
  if (cell) cell.textContent = input.dataset.original;
});

// Modal: open/close via data-modal-open="<dialog id>" / data-modal-close,
// plus a click on the native ::backdrop (target === the <dialog> itself).
document.addEventListener("click", (e) => {
  const opener = e.target.closest("[data-modal-open]");
  if (opener) {
    document.getElementById(opener.dataset.modalOpen)?.showModal();
    return;
  }
  const closer = e.target.closest("[data-modal-close]");
  if (closer) {
    closer.closest("dialog")?.close();
    return;
  }
  if (e.target.tagName === "DIALOG") {
    e.target.close();
  }
});

// Modal forms (data-modal-form): after a successful htmx submit, close the
// dialog and reset the fields so the modal starts empty next time it opens.
// Ignores GET requests so a nested live-search input (e.g. the resolve
// modal's pair picker) doesn't close the modal just by being focused/typed in.
document.body.addEventListener("htmx:afterRequest", (e) => {
  const form = e.target.closest?.("[data-modal-form]");
  if (!form || !e.detail.successful) return;
  if (e.detail.requestConfig?.verb === "get") return;
  form.closest("dialog")?.close();
  form.reset();
});

// Category filter chips: multi-select OR filter over recurring-rule rows.
// The chip bar lives outside the htmx-swapped #recurring-list, so selection
// survives every post/skip/delete/inline-edit refresh; re-applied below.
function applyCategoryFilter() {
  const bar = document.querySelector("[data-category-filter-bar]");
  if (!bar) return;
  const active = Array.from(bar.querySelectorAll(".chip.active")).map(
    (chip) => chip.dataset.categoryChip
  );
  document.querySelectorAll("#recurring-list tr[data-category]").forEach((row) => {
    row.style.display = active.length === 0 || active.includes(row.dataset.category) ? "" : "none";
  });
}

document.addEventListener("click", (e) => {
  const chip = e.target.closest("[data-category-chip]");
  if (!chip) return;
  chip.classList.toggle("active");
  applyCategoryFilter();
});

document.body.addEventListener("htmx:afterSwap", applyCategoryFilter);

// htmx-fetched modals: each lives in an always-present empty container that
// htmx swaps the <dialog> markup into; call showModal() explicitly (rather
// than the `open` attribute) so it gets a real backdrop and native
// Escape-to-close.
const HTMX_MODAL_CONTAINERS = {
  "resolve-modal-container": "resolve-modal",
  "config-modal-container": "config-modal",
  "notes-modal-container": "notes-modal",
};
document.body.addEventListener("htmx:afterSwap", (e) => {
  const dialogId = HTMX_MODAL_CONTAINERS[e.target.id];
  if (dialogId) {
    document.getElementById(dialogId)?.showModal();
  }
});

// Pair picker (resolve modal): clicking a search result fills the hidden
// resolved_txn_id field and the visible search box, then clears the results;
// the clear ("×") button resets the picker back to unset.
document.addEventListener("click", (e) => {
  const item = e.target.closest("[data-pair-candidate]");
  if (item) {
    const picker = item.closest(".pair-picker");
    picker.querySelector("[data-pair-hidden]").value = item.dataset.pairId;
    picker.querySelector("[data-pair-search]").value = item.dataset.pairLabel;
    picker.querySelector("[data-pair-results]").innerHTML = "";
    return;
  }
  const clear = e.target.closest("[data-pair-clear]");
  if (clear) {
    const picker = clear.closest(".pair-picker");
    picker.querySelector("[data-pair-hidden]").value = "";
    picker.querySelector("[data-pair-search]").value = "";
    picker.querySelector("[data-pair-results]").innerHTML = "";
  }
});
