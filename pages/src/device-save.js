import { safeName } from "./classification.js";

const types = {
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  gif: "image/gif",
  webp: "image/webp",
  bmp: "image/bmp",
  heic: "image/heic",
  heif: "image/heif",
  mp4: "video/mp4",
  m4v: "video/mp4",
  mov: "video/quicktime",
  webm: "video/webm",
};

export function deviceItems(media, kids, { children, ids, start, end }) {
  if (start && end && start > end)
    throw new Error("저장할 기간을 확인해 주세요.");
  const names = new Map(
    kids.filter((k) => children.includes(k.id)).map((k) => [k.id, k.name]),
  );
  if (!names.size) throw new Error("저장할 아이를 선택해 주세요.");
  const items = [];
  for (const m of media) {
    if (m.deletedAt || !["organized", "review"].includes(m.state)) continue;
    if (
      (ids && !ids.has(m.id)) ||
      (start && m.captured < start) ||
      (end && m.captured > end)
    )
      continue;
    const matching = m.children.filter((id) => names.has(id));
    if (matching.length)
      items.push({
        media: m,
        prefix: matching.map((id) => names.get(id)).join("_"),
      });
  }
  return items.sort(
    (a, b) =>
      a.media.captured.localeCompare(b.media.captured) ||
      a.media.name.localeCompare(b.media.name),
  );
}

// Read one group of original blobs at a time, including libraries where MIME or File.name was lost.
export async function readDeviceBatch(vault, items, start) {
  const files = [],
    missing = [];
  let end = start,
    bytes = 0;
  while (end < items.length && end - start < 10) {
    const { media, prefix } = items[end];
    const original = await vault.get("originals", media.id);
    if (!original?.size) {
      missing.push(media.name);
      end++;
      continue;
    }
    if (files.length && bytes + original.size > 32 * 1024 * 1024) break;
    const ext = /\.([a-z0-9]{1,8})$/i.exec(media.name)?.[1] || "";
    const stem = ext ? media.name.slice(0, -(ext.length + 1)) : media.name;
    const type =
      types[ext.toLowerCase()] || original.type || "application/octet-stream";
    const filename =
      safeName(prefix).slice(0, 32) +
      "_" +
      String(end + 1) +
      "_" +
      safeName(stem).slice(0, 40) +
      (ext ? "." + ext : "");
    files.push(
      new File([original], filename, {
        type,
        lastModified: original.lastModified || media.created || Date.now(),
      }),
    );
    bytes += original.size;
    end++;
  }
  return { files, end, missing };
}

export function supportsFileShare(browser, files) {
  if (!files.length || !browser.share || !browser.canShare) return false;
  try {
    return browser.canShare({ files });
  } catch {
    return false;
  }
}

export function openDeviceSave(project, media, kids, options) {
  const items = deviceItems(media, kids, options);
  if (!items.length)
    throw new Error("선택한 아이와 기간에 저장할 분류 결과가 없습니다.");
  const dialog = document.createElement("dialog");
  dialog.id = "device-save-dialog";
  dialog.setAttribute("aria-labelledby", "device-save-heading");
  dialog.innerHTML = `<div class="modal-header"><h2 id="device-save-heading">기기에 저장</h2>
    <button type="button" class="icon-button" aria-label="닫기">×</button></div>
    <div class="device-save-body"><p class="device-scope"></p>
    <p>아이폰 공유 메뉴에서 ‘이미지 저장’ 또는 ‘파일에 저장’을 선택하세요. 아이 이름은 파일명에 들어갑니다. 사진 앱에서는 저장 후 원하는 앨범에 추가할 수 있습니다.</p>
    <p role="status" aria-live="polite"></p><div class="device-controls"></div>
    <details><summary>원본 하나씩 저장</summary><div class="device-files"></div></details>
    <p class="input-help">아이별·날짜별 폴더를 그대로 보관하려면 ‘학부모 보내기’에서 ZIP을 내려받으세요.</p>
    <div class="device-pages"></div></div>`;
  const find = (selector) => dialog.querySelector(selector);
  const status = find('[role="status"]'),
    controls = find(".device-controls");
  const list = find(".device-files"),
    pages = find(".device-pages");
  const starts = [0],
    urls = [];
  let pageIndex = 0;
  const release = () => {
    for (const url of urls.splice(0)) URL.revokeObjectURL(url);
  };
  find(".icon-button").onclick = () => dialog.close();
  dialog.onclose = () => {
    release();
    dialog.remove();
  };
  const childNames = kids
    .filter((k) => options.children.includes(k.id))
    .map((k) => k.name);
  find(".device-scope").textContent =
    childNames.join(", ") + " · 원본 " + items.length + "개";
  document.body.append(dialog);
  dialog.showModal();

  function button(parent, label, click, primary = false) {
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = label;
    if (primary) b.className = "primary";
    b.onclick = click;
    parent.append(b);
  }
  // Safari needs a fresh tap after IndexedDB reads; share only already-prepared File objects.
  async function share(files) {
    try {
      project.v.check();
      await navigator.share({ files });
      if (dialog.open)
        status.textContent =
          "공유 메뉴가 닫혔습니다. 저장한 앱에서 결과를 확인하세요.";
    } catch (error) {
      if (dialog.open)
        status.textContent =
          error.name === "AbortError"
            ? "공유를 취소했습니다. 같은 묶음을 다시 선택할 수 있습니다."
            : "공유 메뉴를 열지 못했습니다. 원본을 하나씩 내려받거나 아이별 ZIP을 이용하세요.";
    }
  }
  async function loadPage() {
    release();
    for (const node of [controls, list, pages]) node.replaceChildren();
    status.textContent = "저장할 원본을 준비하고 있습니다…";
    const start = starts[pageIndex];
    try {
      const { files, end, missing } = await readDeviceBatch(
        project.v,
        items,
        start,
      );
      if (!dialog.open) return;
      project.v.check();
      const canShareBatch = supportsFileShare(navigator, files);
      status.textContent =
        `${start + 1}–${end} / ${items.length}개` +
        (missing.length
          ? ` · 원본을 찾을 수 없는 파일 ${missing.length}개`
          : "") +
        (canShareBatch ? "" : " · 아래 파일명을 눌러 원본을 내려받으세요.");
      if (canShareBatch)
        button(
          controls,
          `사진 앱·파일에 저장 (${files.length}개)`,
          () => share(files),
          true,
        );
      find("details").open = !canShareBatch;
      for (const file of files) {
        const row = document.createElement("div"),
          link = document.createElement("a");
        link.href = URL.createObjectURL(file);
        urls.push(link.href);
        link.download = file.name;
        link.textContent = file.name;
        row.append(link);
        if (supportsFileShare(navigator, [file]))
          button(row, "공유·저장", () => share([file]));
        list.append(row);
      }
      if (pageIndex > 0)
        button(pages, "이전 묶음", () => {
          pageIndex--;
          loadPage();
        });
      if (end < items.length)
        button(pages, "다음 묶음", () => {
          starts[++pageIndex] = end;
          loadPage();
        });
    } catch (error) {
      if (dialog.open) {
        status.textContent = error.message;
        button(controls, "다시 준비", loadPage);
      }
    }
  }
  loadPage();
}
