const state = {
  indexUrl: document.getElementById("index-url").value,
  streams: [],
  products: new Map(),
  selectedStream: null,
  selectedProducts: new Set(),
};

const panels = document.querySelectorAll("section[data-tab-panel]");
const tabs = document.querySelectorAll(".p-tabs__link");
const notification = document.getElementById("notification");
const notificationTitle = document.getElementById("notification-title");
const notificationBody = document.getElementById("notification-body");

function showNotification(title, message, tone = "positive") {
  notification.className = `p-notification--${tone}`;
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

  body.innerHTML = "";
  toggleAll.checked = false;

  if (!state.selectedStream) {
    title.textContent = "Products";
    body.innerHTML = "<tr><td colspan='5'>Select a stream to view products.</td></tr>";
    return;
  }

  const products = state.products.get(state.selectedStream) ?? [];
  title.textContent = `Products in ${state.selectedStream}`;

  if (!products.length) {
    body.innerHTML = "<tr><td colspan='5'>No products available.</td></tr>";
    return;
  }

  products.forEach((product) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><input type="checkbox" data-product="${product.product_id}" /></td>
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
        toggleAll.checked = false;
      }
    });
  });

  toggleAll.addEventListener("change", () => {
    const isChecked = toggleAll.checked;
    state.selectedProducts.clear();
    body.querySelectorAll("input[type='checkbox']").forEach((checkbox) => {
      checkbox.checked = isChecked;
      if (isChecked) {
        state.selectedProducts.add(checkbox.dataset.product);
      }
    });
  });
}

async function mirrorSelected() {
  if (!state.selectedProducts.size) {
    showNotification("No products selected", "Select at least one product to mirror.", "negative");
    return;
  }
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
    const successCount = result.mirrored_image_ids.length;
    const failureCount = result.failed.length;
    let message = `${successCount} image(s) mirrored.`;
    if (failureCount) {
      message += ` ${failureCount} item(s) failed.`;
      console.warn(result.failed);
    }
    showNotification("Mirror complete", message, failureCount ? "caution" : "positive");
    state.selectedProducts.clear();
    document.getElementById("mirror-form").reset();
    await refreshLibrary();
  } catch (error) {
    console.error(error);
    showNotification("Mirror failed", error.message, "negative");
  }
}

async function refreshLibrary() {
  const table = document.getElementById("library-table-body");
  table.innerHTML = "<tr><td colspan='10'>Loading…</td></tr>";
  try {
    const response = await fetch("/api/images");
    if (!response.ok) {
      throw new Error(`Failed to load library (${response.status})`);
    }
    const data = await response.json();
    table.innerHTML = "";
    if (!data.items.length) {
      table.innerHTML = "<tr><td colspan='10'>No images mirrored yet.</td></tr>";
      return;
    }
    data.items.forEach((image) => {
  const versionText = image.version ? ` (${image.version})` : "";
  const subarches = image.subarches ?? "";
      const kernelParts = [image.kflavor, image.krel].filter(Boolean);
      const kernelSummary = kernelParts.join(" • ");
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${image.name}</td>
        <td><code>${image.product_id}</code></td>
        <td>${image.image_type}</td>
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
  } catch (error) {
    console.error(error);
    showNotification("Unable to load library", error.message, "negative");
  }
}

async function deleteImage(id) {
  try {
    const response = await fetch(`/api/images/${id}`, { method: "DELETE" });
    if (!response.ok) {
      throw new Error(`Failed to delete image (${response.status})`);
    }
    showNotification("Image removed", "The image and its artifacts were deleted.");
    await refreshLibrary();
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
    await refreshLibrary();
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
});

document.getElementById("custom-form").addEventListener("submit", submitCustomForm);

// Initial load
loadStreams(state.indexUrl);
refreshLibrary();
loadSimplestreamInfo();
