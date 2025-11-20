const state = {
  indexUrl: document.getElementById("index-url").value,
  streams: [],
  products: new Map(),
  selectedStream: null,
  selectedProducts: new Set(),
  productFilter: "",
  jobs: [],
  libraryRefreshHandle: null,
  isRefreshingLibrary: false,
  isRefreshingJobs: false,
  lastLibraryPending: false,
  lastJobsPending: false,
  collapsedReleases: new Set(),
  collapsedArchGroups: new Set(),
};

const panels = document.querySelectorAll("section[data-tab-panel]");
const tabs = document.querySelectorAll(".p-tabs__link");
const notification = document.getElementById("notification");
const notificationTitle = document.getElementById("notification-title");
const notificationBody = document.getElementById("notification-body");
const productCollator = new Intl.Collator(undefined, { numeric: true, sensitivity: "base" });

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

function sortUpstreamProducts(items) {
  return [...items].sort((a, b) => {
    const buildA = a.build_id ?? "";
    const buildB = b.build_id ?? "";
    const buildCompare = productCollator.compare(buildB, buildA);
    if (buildCompare !== 0) {
      return buildCompare;
    }

    const releaseA = a.release ?? "";
    const releaseB = b.release ?? "";
    const releaseCompare = productCollator.compare(releaseB, releaseA);
    if (releaseCompare !== 0) {
      return releaseCompare;
    }

    const versionA = a.version ?? "";
    const versionB = b.version ?? "";
    const versionCompare = productCollator.compare(versionB, versionA);
    if (versionCompare !== 0) {
      return versionCompare;
    }

    return productCollator.compare(b.product_id, a.product_id);
  });
}

function getProductGroupLabel(product) {
  const release = product.release || "Unknown release";
  const osName = product.os ? ` (${product.os})` : "";
  return `${release}${osName}`;
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

function getArchitectureLabel(product) {
  const arch = product.arch || "Unknown architecture";
  if (product.subarch) {
    return `${arch} (${product.subarch})`;
  }
  return arch;
}

function getReleaseKey(product) {
  return getProductGroupLabel(product);
}

function getArchKey(releaseLabel, archLabel) {
  return `${releaseLabel}::${archLabel}`;
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
  const container = document.getElementById("streams-list");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  if (!state.streams.length) {
    container.innerHTML = `<p class="u-text--muted">No streams found for ${state.indexUrl}</p>`;
    return;
  }
  state.streams.forEach((stream) => {
    const item = document.createElement("div");
    item.className = "stream-item";
    if (state.selectedStream === stream.stream_id) {
      item.classList.add("is-active");
    }
    item.dataset.streamId = stream.stream_id;

    const idSpan = document.createElement("span");
    idSpan.className = "stream-item__id";
    idSpan.textContent = stream.stream_id;

    const metaSpan = document.createElement("span");
    metaSpan.className = "stream-item__meta";
    metaSpan.textContent = `${stream.products.length} product(s)`;
    if (stream.updated) {
      metaSpan.textContent += ` • Updated: ${stream.updated}`;
    }

    item.appendChild(idSpan);
    item.appendChild(metaSpan);
    container.appendChild(item);

    item.addEventListener("click", async () => {
      await loadProducts(stream.stream_id);
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
    state.collapsedReleases = new Set(products.map((product) => getReleaseKey(product)));
    state.collapsedArchGroups = new Set(
      products.map((product) => getArchKey(getReleaseKey(product), getArchitectureLabel(product)))
    );
    const filterInput = document.getElementById("product-filter");
    if (filterInput) {
      filterInput.value = "";
    }
    renderStreams();
    renderProducts();
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

  body.innerHTML = "";
  toggleAll.checked = false;
  toggleAll.indeterminate = false;
  toggleAll.disabled = false;

  if (!state.selectedStream) {
    title.textContent = "Products";
    summary.textContent = "Select a stream to view products.";
    body.innerHTML = "<tr><td colspan='5'>Select a stream to view products.</td></tr>";
    toggleAll.disabled = true;
    return;
  }

  const filtered = getFilteredProducts();
  const products = sortUpstreamProducts(filtered);

  title.textContent = `Products in ${state.selectedStream}`;

  if (!products.length) {
    summary.textContent = state.productFilter
      ? "No products match your filters."
      : "No products available for this stream.";
    body.innerHTML = "<tr><td colspan='5'>No products available.</td></tr>";
    toggleAll.disabled = true;
    return;
  }

  const selectedInFiltered = products.reduce(
    (count, product) => (state.selectedProducts.has(product.product_id) ? count + 1 : count),
    0
  );

  summary.textContent = `Found ${products.length} product(s). Selected: ${selectedInFiltered}.`;
  toggleAll.checked = selectedInFiltered > 0 && selectedInFiltered === products.length;
  toggleAll.indeterminate = selectedInFiltered > 0 && selectedInFiltered < products.length;
  toggleAll.disabled = products.length === 0;

  const releaseCounts = new Map();
  const archCounts = new Map();
  products.forEach((product) => {
    const releaseLabel = getReleaseKey(product);
    const archLabel = getArchitectureLabel(product);
    const archKey = getArchKey(releaseLabel, archLabel);
    releaseCounts.set(releaseLabel, (releaseCounts.get(releaseLabel) || 0) + 1);
    archCounts.set(archKey, (archCounts.get(archKey) || 0) + 1);
  });

  let lastRelease = null;
  let lastArch = null;
  products.forEach((product) => {
    const releaseLabel = getReleaseKey(product);
    const releaseCollapsed = state.collapsedReleases.has(releaseLabel);
    if (releaseLabel !== lastRelease) {
      const releaseRow = document.createElement("tr");
      releaseRow.className = "products-release-row";
      const releaseCell = document.createElement("td");
      releaseCell.colSpan = 5;
      releaseCell.className = "products-release-cell";

      const releaseButton = document.createElement("button");
      releaseButton.type = "button";
      releaseButton.className = "group-toggle";
      releaseButton.dataset.releaseToggle = releaseLabel;
      releaseButton.setAttribute("aria-expanded", String(!releaseCollapsed));

      const iconSpan = document.createElement("span");
      iconSpan.className = "group-toggle__icon";
      iconSpan.textContent = releaseCollapsed ? "▶" : "▼";

      const labelSpan = document.createElement("span");
      labelSpan.className = "group-toggle__label";
      labelSpan.textContent = releaseLabel;

      const countSpan = document.createElement("span");
      countSpan.className = "group-toggle__count";
      countSpan.textContent = `${releaseCounts.get(releaseLabel) ?? 0} item(s)`;

      releaseButton.append(iconSpan, labelSpan, countSpan);
      releaseCell.appendChild(releaseButton);
      releaseRow.appendChild(releaseCell);
      body.appendChild(releaseRow);
      lastRelease = releaseLabel;
      lastArch = null;
    }

    if (releaseCollapsed) {
      return;
    }

    const archLabel = getArchitectureLabel(product);
    const archKey = getArchKey(releaseLabel, archLabel);
    const archCollapsed = state.collapsedArchGroups.has(archKey);

    if (archLabel !== lastArch) {
      const archRow = document.createElement("tr");
      archRow.className = "products-arch-row";

      const archCell = document.createElement("td");
      archCell.colSpan = 5;
      archCell.className = "products-arch-cell";

      const archButton = document.createElement("button");
      archButton.type = "button";
      archButton.className = "group-toggle group-toggle--arch";
      archButton.dataset.archToggle = archKey;
      archButton.setAttribute("aria-expanded", String(!archCollapsed));

      const archIcon = document.createElement("span");
      archIcon.className = "group-toggle__icon";
      archIcon.textContent = archCollapsed ? "▶" : "▼";

      const archLabelSpan = document.createElement("span");
      archLabelSpan.className = "group-toggle__label";
      archLabelSpan.textContent = archLabel;

      const archCountSpan = document.createElement("span");
      archCountSpan.className = "group-toggle__count";
      archCountSpan.textContent = `${archCounts.get(archKey) ?? 0} item(s)`;

      archButton.append(archIcon, archLabelSpan, archCountSpan);
      archCell.appendChild(archButton);
      archRow.appendChild(archCell);
      body.appendChild(archRow);
      lastArch = archLabel;
    }

    if (archCollapsed) {
      return;
    }

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

  body.querySelectorAll("button[data-release-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.releaseToggle;
      if (!key) {
        return;
      }
      if (state.collapsedReleases.has(key)) {
        state.collapsedReleases.delete(key);
      } else {
        state.collapsedReleases.add(key);
      }
      renderProducts();
    });
  });

  body.querySelectorAll("button[data-arch-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const key = button.dataset.archToggle;
      if (!key) {
        return;
      }
      if (state.collapsedArchGroups.has(key)) {
        state.collapsedArchGroups.delete(key);
      } else {
        state.collapsedArchGroups.add(key);
      }
      renderProducts();
    });
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
      const filteredProducts = sortUpstreamProducts(getFilteredProducts());
      if (!toggleAll.checked) {
        filteredProducts.forEach((product) => {
          state.selectedProducts.delete(product.product_id);
        });
      } else {
        filteredProducts.forEach((product) => {
          state.selectedProducts.add(product.product_id);
        });
      }
      renderProducts();
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
    table.innerHTML = "<tr><td colspan='8'>Loading…</td></tr>";
  }

  try {
    const response = await fetch("/api/images");
    if (!response.ok) {
      throw new Error(`Failed to load library (${response.status})`);
    }
    const data = await response.json();
    table.innerHTML = "";

    if (!data.items.length) {
      table.innerHTML = "<tr><td colspan='8'>No images mirrored yet.</td></tr>";
      state.lastLibraryPending = false;
      return false;
    }

    let hasPending = false;

    data.items.forEach((image) => {
      const versionText = image.version ? ` v${image.version}` : "";
      const statusBadge = renderStatusBadge(image.status, image.status_detail);
      if ((image.status || "").toLowerCase() !== "ready") {
        hasPending = true;
      }

      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${image.name}</td>
        <td><code style="font-size: 0.85rem;">${image.product_id}</code></td>
        <td>${image.image_type}</td>
        <td>${statusBadge}</td>
        <td>${image.release ?? ""}${versionText}</td>
        <td>${image.arch ?? ""}</td>
        <td>
          ${image.artifacts
            .map(
              (artifact) =>
                `<a href="${artifact.download_url}" target="_blank" rel="noopener">${artifact.name}</a>`
            )
            .join(", ")}
        </td>
        <td><button class="p-button--base is-small" data-delete="${image.id}">Remove</button></td>
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
      table.innerHTML = `<tr><td colspan='8'>${error.message}</td></tr>`;
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

  const container = document.getElementById("jobs-list");
  if (!container) {
    state.isRefreshingJobs = false;
    return state.lastJobsPending;
  }

  if (!silent) {
    container.innerHTML = "<p class='u-text--muted'>Loading jobs…</p>";
  }

  try {
    const response = await fetch("/api/mirror/jobs");
    if (!response.ok) {
      throw new Error(`Failed to load mirror jobs (${response.status})`);
    }

    const data = await response.json();
    const items = data.items ?? [];
    container.innerHTML = "";

    if (!items.length) {
      container.innerHTML = "<p class='u-text--muted'>No mirror jobs yet.</p>";
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

      const jobCard = document.createElement("div");
      jobCard.className = "job-item";

      const header = document.createElement("div");
      header.className = "job-item__header";

      const jobId = document.createElement("span");
      jobId.className = "job-item__id";
      jobId.textContent = `Job #${job.id}`;

      const statusBadge = document.createElement("span");
      statusBadge.innerHTML = renderStatusBadge(job.status, null);

      header.appendChild(jobId);
      header.appendChild(statusBadge);

      const productLine = document.createElement("div");
      productLine.className = "job-item__product";
      productLine.textContent = job.product_id;

      const details = document.createElement("div");
      details.className = "job-item__details";

      if (job.message) {
        const messageLine = document.createElement("div");
        messageLine.textContent = job.message;
        messageLine.style.color = "#c7162b";
        details.appendChild(messageLine);
      }

      const createdLine = document.createElement("div");
      createdLine.textContent = `Created: ${formatDateTime(job.created_at)}`;
      details.appendChild(createdLine);

      if (job.started_at) {
        const startedLine = document.createElement("div");
        startedLine.textContent = `Started: ${formatDateTime(job.started_at)}`;
        details.appendChild(startedLine);
      }

      if (job.finished_at) {
        const finishedLine = document.createElement("div");
        finishedLine.textContent = `Finished: ${formatDateTime(job.finished_at)}`;
        details.appendChild(finishedLine);
      }

      jobCard.appendChild(header);
      jobCard.appendChild(productLine);
      jobCard.appendChild(details);

      if (job.progress !== null && job.progress !== undefined) {
        const progressContainer = document.createElement("div");
        progressContainer.className = "job-item__progress";

        const progressBar = document.createElement("div");
        progressBar.className = "job-item__progress-bar";

        const progressFill = document.createElement("div");
        progressFill.className = "job-item__progress-fill";
        const numericProgress = Number(job.progress);
        if (!Number.isNaN(numericProgress)) {
          progressFill.style.width = `${Math.max(0, Math.min(100, numericProgress))}%`;
        }

        progressBar.appendChild(progressFill);
        progressContainer.appendChild(progressBar);
        jobCard.appendChild(progressContainer);
      }

      container.appendChild(jobCard);
    });

    state.jobs = items;
    state.lastJobsPending = hasPending;
    return hasPending;
  } catch (error) {
    console.error(error);
    if (!silent) {
      container.innerHTML = `<p class='u-text--muted'>${error.message}</p>`;
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
  const progressContainer = document.getElementById("upload-progress-container");
  const progressBar = document.getElementById("upload-progress-bar");
  const progressText = document.getElementById("upload-progress-text");
  
  // Show progress UI
  progressContainer.classList.remove("u-hide");
  progressBar.style.width = "0%";
  progressText.textContent = "Preparing upload...";
  
  try {
    // Use XMLHttpRequest for progress tracking
    const result = await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      
      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable) {
          const percentComplete = (e.loaded / e.total) * 100;
          progressBar.style.width = percentComplete + "%";
          
          if (percentComplete < 100) {
            const mbLoaded = (e.loaded / 1024 / 1024).toFixed(1);
            const mbTotal = (e.total / 1024 / 1024).toFixed(1);
            progressText.textContent = `Uploading: ${mbLoaded} MB / ${mbTotal} MB (${Math.round(percentComplete)}%)`;
          } else {
            progressText.textContent = "Processing upload...";
          }
        }
      });
      
      xhr.addEventListener("load", () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const data = JSON.parse(xhr.responseText);
            resolve(data);
          } catch (e) {
            resolve({});
          }
        } else {
          try {
            const details = JSON.parse(xhr.responseText);
            reject(new Error(details.detail ?? `Upload failed (${xhr.status})`));
          } catch (e) {
            reject(new Error(`Upload failed (${xhr.status})`));
          }
        }
      });
      
      xhr.addEventListener("error", () => {
        reject(new Error("Network error during upload"));
      });
      
      xhr.addEventListener("abort", () => {
        reject(new Error("Upload cancelled"));
      });
      
      xhr.open("POST", "/api/custom/images");
      xhr.send(formData);
    });
    
    form.reset();
    progressContainer.classList.add("u-hide");
    showNotification("Custom image published", "The simplestream metadata has been updated.");
    switchTab("library");
    const [libraryPending, jobsPending] = await Promise.all([refreshLibrary(), refreshJobs()]);
    ensureLibraryPolling(Boolean(libraryPending || jobsPending));
  } catch (error) {
    console.error(error);
    progressContainer.classList.add("u-hide");
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
