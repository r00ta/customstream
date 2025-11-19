const state = {
  indexUrl: document.getElementById("index-url").value,
  streams: [],
  products: new Map(),
  selectedStream: null,
  selectedProducts: new Set(),
  productFilter: "",
  productPage: 1,
  productPageSize: 10,
  jobs: [],
  libraryRefreshHandle: null,
  isRefreshingLibrary: false,
  isRefreshingJobs: false,
  lastLibraryPending: false,
  lastJobsPending: false,
};

const panels = document.querySelectorAll("section[data-tab-panel]");
const tabs = document.querySelectorAll(".p-tabs__link");
const notification = document.getElementById("notification");
const notificationTitle = document.getElementById("notification-title");
const notificationBody = document.getElementById("notification-body");

function showNotification(title, message, tone = "positive") {
  notification.className = `p-notification p-notification--${tone}`;
  notificationTitle.textContent = title;
  notificationBody.textContent = message;
  notification.classList.remove("u-hide");
  setTimeout(() => notification.classList.add("u-hide"), 5000);
}

function setFormBusy(form, busy) {
  const submitButton = form.querySelector("button[type='submit']");
  if (submitButton) {
    submitButton.disabled = busy;
    submitButton.setAttribute("aria-busy", String(busy));
  }
}

function validateCustomForm(form) {
  if (!form.reportValidity()) {
    return false;
  }
  const files = ["kernel", "initrd", "rootfs", "manifest"].map((name) => {
    const input = form.querySelector(`[name="${name}"]`);
    return input && input.files ? input.files.length : 0;
  });
  if (!files.some((count) => count > 0)) {
    showNotification("Artifacts required", "Upload at least one artifact before publishing.", "negative");
    return false;
  }
  const rootfsInput = form.querySelector('[name="rootfs"]');
  const manifestInput = form.querySelector('[name="manifest"]');
  const hasRootfs = rootfsInput && rootfsInput.files ? rootfsInput.files.length > 0 : false;
  const hasManifest = manifestInput && manifestInput.files ? manifestInput.files.length > 0 : false;
  if (hasRootfs && !hasManifest) {
    showNotification(
      "Manifest required",
      "Include the matching squashfs.manifest when uploading a root filesystem.",
      "negative"
    );
    return false;
  }
  return true;
}

function renderStatusBadge(status, detail) {
  const normalized = (status || "").toLowerCase();
  const tone = {
    ready: "positive",
    mirroring: "information",
    pending: "caution",
    error: "negative",
    queued: "caution",
    running: "information",
    completed: "positive",
    failed: "negative",
  }[normalized] || "information";

  const label = {
    ready: "Ready",
    mirroring: "Mirroring",
    pending: "Pending",
    error: "Error",
    queued: "Queued",
    running: "Running",
    completed: "Completed",
    failed: "Failed",
  }[normalized] || status || "Unknown";

  const detailClass = normalized === "error" || normalized === "failed" ? "status-detail status-detail--error" : "status-detail";
  const detailHtml = detail ? `<span class="${detailClass}">${detail}</span>` : "";
  return `<span class="p-badge p-badge--${tone}">${label}</span>${detailHtml}`;
}

function formatDateTime(value) {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function ensureLibraryPolling(pending) {
  if (pending && !state.libraryRefreshHandle) {
    state.libraryRefreshHandle = setInterval(() => {
      Promise.all([refreshLibrary(true), refreshJobs(true)])
        .then(([libraryPending, jobsPending]) => {
          if (!libraryPending && !jobsPending) {
            ensureLibraryPolling(false);
          }
        })
        .catch((error) => {
          console.error(error);
        });
    }, 5000);
  }

  if (!pending && state.libraryRefreshHandle) {
    clearInterval(state.libraryRefreshHandle);
    state.libraryRefreshHandle = null;
  }
}

function getFilteredProducts() {
  if (!state.selectedStream) {
    return [];
  }
  const products = state.products.get(state.selectedStream) ?? [];
  if (!state.productFilter) {
    return products;
  }
  const query = state.productFilter.toLowerCase();
  return products.filter((product) => {
    const haystack = [
      product.product_id,
      product.os,
      product.release,
      product.version,
      product.arch,
      product.subarch,
      product.label,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
}

function switchTab(target) {
  tabs.forEach((tab) => {
    tab.classList.toggle("is-active", tab.dataset.tab === target);
  });
  panels.forEach((panel) => {
    panel.classList.toggle("u-hide", panel.dataset.tabPanel !== target);
  });
}

tabs.forEach((tab) => {
  tab.addEventListener("click", () => switchTab(tab.dataset.tab));
});

async function loadStreams(indexUrl) {
  try {
    const response = await fetch(`/api/upstream/streams?index_url=${encodeURIComponent(indexUrl)}`);
    if (!response.ok) {
      throw new Error(`Failed to fetch streams (${response.status})`);
    }
    state.streams = await response.json();
    state.indexUrl = indexUrl;
    renderStreams();
    showNotification("Streams loaded", "Select a stream to inspect its products.");
  } catch (error) {
    console.error(error);
    showNotification("Unable to load streams", error.message, "negative");
  }
}

function renderStreams() {
  const body = document.getElementById("streams-table-body");
  body.innerHTML = "";
  if (!state.streams.length) {
    body.innerHTML = `<tr><td colspan="4">No streams found for ${state.indexUrl}</td></tr>`;
    return;
  }
  state.streams.forEach((stream) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><code>${stream.stream_id}</code></td>
      <td>${stream.products.length}</td>
      <td>${stream.updated ?? ""}</td>
      <td><button class="p-button--base" data-stream="${stream.stream_id}">View products</button></td>
    `;
    body.appendChild(row);
  });

  body.querySelectorAll("button[data-stream]").forEach((button) => {
    button.addEventListener("click", async () => {
      const streamId = button.dataset.stream;
      await loadProducts(streamId);
    });
  });
}

async function loadProducts(streamId) {
  try {
    const response = await fetch(
      `/api/upstream/streams/${encodeURIComponent(streamId)}/products?index_url=${encodeURIComponent(state.indexUrl)}`
    );
    if (!response.ok) {
      throw new Error(`Failed to load products (${response.status})`);
    }
    const products = await response.json();
    state.products.set(streamId, products);
    state.selectedStream = streamId;
    state.selectedProducts.clear();
    state.productFilter = "";
    state.productPage = 1;
    const filterInput = document.getElementById("product-filter");
    if (filterInput) {
      filterInput.value = "";
    }
    renderProducts();
    switchTab("mirror");
  } catch (error) {
    console.error(error);
    showNotification("Unable to load products", error.message, "negative");
  }
}

function renderProducts() {
  const title = document.getElementById("products-title");
  const body = document.getElementById("products-table-body");
  const toggleAll = document.getElementById("toggle-all");
  const summary = document.getElementById("products-summary");
  const pageIndicator = document.getElementById("products-page-indicator");
  const prevButton = document.getElementById("products-page-prev");
  const nextButton = document.getElementById("products-page-next");

  body.innerHTML = "";
  toggleAll.checked = false;
  toggleAll.indeterminate = false;

  if (!state.selectedStream) {
    title.textContent = "Products";
    summary.textContent = "Select a stream to view products.";
    body.innerHTML = "<tr><td colspan='5'>Select a stream to view products.</td></tr>";
    pageIndicator.textContent = "";
    prevButton.disabled = true;
    nextButton.disabled = true;
    return;
  }

  const filtered = getFilteredProducts();
  const products = filtered;
  title.textContent = `Products in ${state.selectedStream}`;

  if (!products.length) {
    summary.textContent = state.productFilter
      ? "No products match your filters."
      : "No products available for this stream.";
    body.innerHTML = "<tr><td colspan='5'>No products available.</td></tr>";
    pageIndicator.textContent = "";
    prevButton.disabled = true;
    nextButton.disabled = true;
    return;
  }

  const total = products.length;
  const pageSize = state.productPageSize;
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (state.productPage > pages) {
    state.productPage = pages;
  }
  if (state.productPage < 1) {
    state.productPage = 1;
  }

  const start = (state.productPage - 1) * pageSize;
  const visible = products.slice(start, start + pageSize);

  const selectedOnPage = visible.filter((product) => state.selectedProducts.has(product.product_id)).length;
  summary.textContent = `Showing ${start + 1}-${start + visible.length} of ${total} product(s). Selected: ${state.selectedProducts.size}`;
  pageIndicator.textContent = `Page ${state.productPage} of ${pages}`;
  prevButton.disabled = state.productPage <= 1;
  nextButton.disabled = state.productPage >= pages;
  toggleAll.checked = visible.length > 0 && selectedOnPage === visible.length;
  toggleAll.indeterminate = selectedOnPage > 0 && selectedOnPage < visible.length;

  visible.forEach((product) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input type="checkbox" data-product="${product.product_id}" ${
        state.selectedProducts.has(product.product_id) ? "checked" : ""
      } /></td>
      <td><code>${product.product_id}</code></td>
      <td>${product.os ?? ""}</td>
      <td>${product.release ?? ""}</td>
      <td>${product.arch ?? ""}</td>
    `;
    body.appendChild(row);
  });

  body.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      const id = checkbox.dataset.product;
      if (checkbox.checked) {
        state.selectedProducts.add(id);
      } else {
        state.selectedProducts.delete(id);
      }
      window.requestAnimationFrame(() => renderProducts());
    });
  });

  if (!toggleAll.dataset.bound) {
    toggleAll.addEventListener("change", () => {
      const isChecked = toggleAll.checked;
      if (!isChecked) {
        body.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
          checkbox.checked = false;
          state.selectedProducts.delete(checkbox.dataset.product);
        });
        window.requestAnimationFrame(() => renderProducts());
        return;
      }

      body.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
        checkbox.checked = true;
        state.selectedProducts.add(checkbox.dataset.product);
      });
      window.requestAnimationFrame(() => renderProducts());
    });
    toggleAll.dataset.bound = "true";
  }
}

async function mirrorSelected() {
  if (!state.selectedProducts.size) {
    showNotification("No products selected", "Select at least one product to mirror.", "negative");
    return;
  }

  const form = document.getElementById("mirror-form");
  setFormBusy(form, true);

  try {
    const response = await fetch("/api/mirror", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        index_url: state.indexUrl,
        product_ids: Array.from(state.selectedProducts),
      }),
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.detail ?? `Mirroring failed (${response.status})`);
    }
    const result = await response.json();
    const enqueued = result.enqueued ?? [];
    const skipped = result.skipped ?? [];
    const jobs = result.jobs ?? [];
    let message = `${enqueued.length} image(s) queued for mirroring.`;
    if (jobs.length) {
      const identifiers = jobs.map((job) => `#${job.job_id}`).join(", ");
      message += ` Jobs: ${identifiers}.`;
    }
    if (skipped.length) {
      message += ` ${skipped.length} item(s) skipped.`;
      console.warn(skipped);
    }
    showNotification("Mirror scheduled", message, skipped.length ? "caution" : "positive");
    state.selectedProducts.clear();
    document.getElementById("mirror-form").reset();
    state.productPage = 1;
    renderProducts();
  const [libraryPending, jobsPending] = await Promise.all([refreshLibrary(), refreshJobs()]);
  ensureLibraryPolling(Boolean(libraryPending || jobsPending));
  } catch (error) {
    console.error(error);
    showNotification("Mirror failed", error.message, "negative");
  } finally {
    setFormBusy(form, false);
  }
}

async function refreshLibrary(silent = false) {
  if (state.isRefreshingLibrary) {
    return state.lastLibraryPending;
  }
  state.isRefreshingLibrary = true;

  const table = document.getElementById("library-table-body");
  if (!silent) {
    table.innerHTML = "<tr><td colspan='11'>Loading…</td></tr>";
  }

  try {
    const response = await fetch("/api/images");
    if (!response.ok) {
      throw new Error(`Failed to load library (${response.status})`);
    }
    const data = await response.json();
    table.innerHTML = "";

    if (!data.items.length) {
      table.innerHTML = "<tr><td colspan='11'>No images mirrored yet.</td></tr>";
      state.lastLibraryPending = false;
      return false;
    }

    let hasPending = false;

    data.items.forEach((image) => {
      const versionText = image.version ? ` (${image.version})` : "";
      const subarches = image.subarches ?? "";
      const kernelParts = [image.kflavor, image.krel].filter(Boolean);
      const kernelSummary = kernelParts.join(" • ");
      const statusBadge = renderStatusBadge(image.status, image.status_detail);
      if ((image.status || "").toLowerCase() !== "ready") {
        hasPending = true;
      }

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${image.name}</td>
        <td><code>${image.product_id}</code></td>
        <td>${image.image_type}</td>
        <td>${statusBadge}</td>
        <td>${image.release ?? ""}${versionText}</td>
        <td>${image.release_codename ?? ""}</td>
        <td>${image.arch ?? ""}</td>
        <td>${subarches}</td>
        <td>${kernelSummary}</td>
        <td>
          ${image.artifacts
            .map(
              (artifact) =>
                `<a href="${artifact.download_url}" target="_blank" rel="noopener">${artifact.name}</a>`
            )
            .join(", ")}
        </td>
        <td><button class="p-button--base" data-delete="${image.id}">Remove</button></td>
      `;
      table.appendChild(row);
    });

    table.querySelectorAll("button[data-delete]").forEach((button) => {
      button.addEventListener("click", async () => {
        const id = button.dataset.delete;
        if (!confirm("Remove this image and delete its artifacts?")) {
          return;
        }
        await deleteImage(id);
      });
    });
    state.lastLibraryPending = hasPending;
    return hasPending;
  } catch (error) {
    console.error(error);
    if (!silent) {
      table.innerHTML = `<tr><td colspan='11'>${error.message}</td></tr>`;
      showNotification("Unable to load library", error.message, "negative");
    }
    state.lastLibraryPending = true;
    return true;
  } finally {
    state.isRefreshingLibrary = false;
  }
}

async function refreshJobs(silent = false) {
  if (state.isRefreshingJobs) {
    return state.lastJobsPending;
  }
  state.isRefreshingJobs = true;

  const table = document.getElementById("jobs-table-body");
  if (!table) {
    state.isRefreshingJobs = false;
    return state.lastJobsPending;
  }

  if (!silent) {
    table.innerHTML = "<tr><td colspan='7'>Loading…</td></tr>";
  }

  try {
    const response = await fetch("/api/mirror/jobs");
    if (!response.ok) {
      throw new Error(`Failed to load mirror jobs (${response.status})`);
    }

    const data = await response.json();
    const items = data.items ?? [];
    table.innerHTML = "";

    if (!items.length) {
      table.innerHTML = "<tr><td colspan='7'>No mirror jobs yet.</td></tr>";
      state.jobs = [];
      state.lastJobsPending = false;
      return false;
    }

    let hasPending = false;

    items.forEach((job) => {
      const statusValue = (job.status || "").toLowerCase();
      if (statusValue === "queued" || statusValue === "running") {
        hasPending = true;
      }

      const statusBadge = renderStatusBadge(job.status, job.message);
      const hasProgress = job.progress !== null && job.progress !== undefined;
      let progressText = "—";
      if (hasProgress) {
        const numericProgress = Number(job.progress);
        if (!Number.isNaN(numericProgress)) {
          progressText = `${Math.max(0, Math.min(100, Math.round(numericProgress)))}%`;
        }
      }

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${job.id}</td>
        <td><code>${job.product_id}</code></td>
        <td>${statusBadge}</td>
        <td>${progressText}</td>
        <td>${formatDateTime(job.created_at)}</td>
        <td>${formatDateTime(job.started_at)}</td>
        <td>${formatDateTime(job.finished_at)}</td>
      `;
      table.appendChild(row);
    });

    state.jobs = items;
    state.lastJobsPending = hasPending;
    return hasPending;
  } catch (error) {
    console.error(error);
    if (!silent) {
      table.innerHTML = `<tr><td colspan='7'>${error.message}</td></tr>`;
      showNotification("Unable to load jobs", error.message, "negative");
    }
    state.lastJobsPending = true;
    return true;
  } finally {
    state.isRefreshingJobs = false;
  }
}

async function deleteImage(id) {
  try {
    const response = await fetch(`/api/images/${id}`, { method: "DELETE" });
    if (!response.ok) {
      throw new Error(`Failed to delete image (${response.status})`);
    }
    showNotification("Image removed", "The image and its artifacts were deleted.");
    const [libraryPending, jobsPending] = await Promise.all([refreshLibrary(), refreshJobs()]);
    ensureLibraryPolling(Boolean(libraryPending || jobsPending));
  } catch (error) {
    console.error(error);
    showNotification("Deletion failed", error.message, "negative");
  }
}

async function submitCustomForm(event) {
  event.preventDefault();
  const form = event.target;
  const formData = new FormData(form);
  if (!validateCustomForm(form)) {
    return;
  }
  setFormBusy(form, true);
  try {
    const response = await fetch("/api/custom/images", {
      method: "POST",
      body: formData,
    });
    if (!response.ok) {
      const details = await response.json().catch(() => ({}));
      throw new Error(details.detail ?? `Upload failed (${response.status})`);
    }
    await response.json();
    form.reset();
    showNotification("Custom image published", "The simplestream metadata has been updated.");
    switchTab("library");
  const [libraryPending, jobsPending] = await Promise.all([refreshLibrary(), refreshJobs()]);
  ensureLibraryPolling(Boolean(libraryPending || jobsPending));
  } catch (error) {
    console.error(error);
    showNotification("Upload failed", error.message, "negative");
  } finally {
    setFormBusy(form, false);
  }
}

async function loadSimplestreamInfo() {
  try {
    const response = await fetch("/api/simplestream");
    if (!response.ok) {
      throw new Error("Unable to fetch simplestream info");
    }
    const data = await response.json();
    const urlElement = document.getElementById("simplestream-url");
    urlElement.textContent = data.index;
  } catch (error) {
    console.warn(error);
  }
}

// Event bindings

document.getElementById("upstream-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const indexUrl = document.getElementById("index-url").value;
  loadStreams(indexUrl);
});

document.getElementById("product-filter").addEventListener("input", (event) => {
  state.productFilter = event.target.value;
  state.productPage = 1;
  renderProducts();
});

document.getElementById("product-page-size").addEventListener("change", (event) => {
  const value = Number.parseInt(event.target.value, 10);
  state.productPageSize = Number.isNaN(value) || value <= 0 ? 10 : value;
  state.productPage = 1;
  renderProducts();
});

document.getElementById("products-page-prev").addEventListener("click", () => {
  if (state.productPage > 1) {
    state.productPage -= 1;
    renderProducts();
  }
});

document.getElementById("products-page-next").addEventListener("click", () => {
  state.productPage += 1;
  renderProducts();
});

document.getElementById("mirror-form").addEventListener("submit", (event) => {
  event.preventDefault();
  mirrorSelected();
});

document.getElementById("clear-selection").addEventListener("click", () => {
  state.selectedProducts.clear();
  document
    .querySelectorAll("#products-table-body input[type='checkbox']")
    .forEach((checkbox) => (checkbox.checked = false));
  document.getElementById("toggle-all").checked = false;
  document.getElementById("toggle-all").indeterminate = false;
  renderProducts();
});

document.getElementById("custom-form").addEventListener("submit", submitCustomForm);

// Initial load
loadStreams(state.indexUrl);
Promise.all([refreshLibrary(), refreshJobs()]).then(([libraryPending, jobsPending]) => {
  ensureLibraryPolling(Boolean(libraryPending || jobsPending));
});
loadSimplestreamInfo();
