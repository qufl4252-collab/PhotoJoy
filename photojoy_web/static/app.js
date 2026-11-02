"use strict";
const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const labels = {
  candidate: "자동 승인 후보",
  review: "사용자 확인",
  confirmed: "검토 완료",
  excluded: "제외",
  no_face: "얼굴 없음",
  error: "분석 오류",
};
const platforms = {
  windows: "윈도우",
  android: "안드로이드",
  iphone: "아이폰",
};
let config = {},
  user = null,
  authMode = "login",
  view = "review",
  library = { children: [], media: [], statistics: [] };
let selected = null,
  currentDetail = null,
  filter = "all",
  search = "",
  sort = "newest",
  uploading = false,
  detailRequest = 0;
const childName = (id) =>
  library.children.find((c) => c.id === id)?.name || "미등록";
const badge = (status) =>
  `<span class="badge ${esc(status)}">${esc(labels[status] || status)}</span>`;
const platform = () =>
  document.querySelector('input[name="platform"]:checked').value;

async function api(path, options = {}) {
  const headers = { ...options.headers };
  if (options.method && options.method !== "GET") headers["X-PhotoJoy"] = "1";
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  const response = await fetch(path, {
    ...options,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && user) {
      user = null;
      showLogin();
    }
    const message =
      typeof data.detail === "string"
        ? data.detail
        : "입력 내용을 확인해 주세요.";
    throw new Error(message);
  }
  return data;
}
function notify(message, error = false) {
  $("notice").textContent = message;
  $("notice").className = "message" + (error ? " error" : "");
  $("notice").hidden = false;
}
function authError(message) {
  $("auth-error").textContent = message;
  $("auth-error").hidden = false;
}
function modal(title, html) {
  $("modal-title").textContent = title;
  $("modal-content").innerHTML = html;
  if (!$("modal").open) $("modal").showModal();
}
function closeModal() {
  $("modal").close();
}
function run(action) {
  return Promise.resolve()
    .then(action)
    .catch((e) => notify(e.message, true));
}
function empty(title, text, button = "") {
  return `<div class="empty"><span class="empty-icon">▧</span><h3>${esc(title)}</h3><p>${esc(text)}</p>${button}</div>`;
}
function mode(value) {
  authMode = value;
  $("auth-error").hidden = true;
  for (const name of ["login", "register"]) {
    $(name + "-tab").classList.toggle("active", name === value);
    $(name + "-tab").setAttribute("aria-selected", String(name === value));
  }
  $("auth-submit").textContent =
    value === "login" ? "로그인 →" : "계정 만들고 시작하기 →";
  $("password").autocomplete =
    value === "login" ? "current-password" : "new-password";
  $("password").minLength = value === "register" ? 10 : 1;
  $("password-help").hidden = value !== "register";
}
function showLogin() {
  $("workspace").hidden = true;
  $("login-screen").hidden = false;
  closeModal();
  $("password").value = "";
  selected = null;
  currentDetail = null;
  library = { children: [], media: [], statistics: [] };
  $("page-content").replaceChildren();
}
async function enter(result) {
  user = result.user;
  $("password").value = "";
  $("auth-error").hidden = true;
  $("login-screen").hidden = true;
  $("workspace").hidden = false;
  $("user-label").textContent = user.display_name + "님";
  $("platform-label").textContent = platforms[user.platform] + "에서 사용 중";
  await refresh();
  navigate("review");
}
async function refresh() {
  library = await api("/api/library");
  const total = library.media.length,
    done = library.media.filter((m) => m.reviewed).length;
  $("total-count").innerHTML = `${total.toLocaleString()}<span>개</span>`;
  $("child-count").innerHTML = `${library.children.length}<span>명</span>`;
  $("confirmed-count").innerHTML = `${done}<span>개</span>`;
  $("review-progress").value = total ? Math.round((done / total) * 100) : 0;
  $("summary-copy").textContent = total
    ? `${total}개 중 ${done}개 검토 완료 · ${total - done}개 확인이 필요해요.`
    : "사진을 추가하고 정리를 시작해 보세요.";
}
function navigate(next) {
  view = next;
  detailRequest++;
  document
    .querySelectorAll("[data-view]")
    .forEach((button) =>
      button.classList.toggle("active", button.dataset.view === next),
    );
  const titles = {
    review: "결과 검토",
    upload: "사진 분류",
    children: "아이 관리",
    export: "보내기 준비",
    statistics: "통계",
  };
  const descriptions = {
    review: "사진 속 아이를 확인하고, 소중한 순간을 아이별로 모아보세요.",
    upload: "기기에 있는 사진과 영상을 선택하면 얼굴을 찾아드려요.",
    children: "아이 이름을 등록하고, 참고 얼굴을 연결해 주세요.",
    export: "확인한 사진을 아이별 ZIP 파일로 내려받으세요.",
    statistics: "아이별로 모인 추억을 한눈에 확인해 보세요.",
  };
  $("page-title").textContent = titles[next];
  $("page-description").textContent = descriptions[next];
  ({
    review: renderReview,
    upload: renderUpload,
    children: renderChildren,
    export: renderExport,
    statistics: renderStatistics,
  })[next]();
}
function renderReview() {
  $("page-content").innerHTML =
    `<div class="review-layout"><section class="panel photo-panel"><div class="toolbar"><div class="filters">${[
      ["all", "전체"],
      ["candidate", "자동 승인 후보"],
      ["pending", "사용자 확인"],
      ["confirmed", "검토 완료"],
    ]
      .map(
        ([id, label]) =>
          `<button data-filter="${id}" class="${filter === id ? "active" : ""}">${label} (${library.media.filter((m) => matchesFilter(m, id)).length})</button>`,
      )
      .join(
        "",
      )}</div></div><div class="search-row"><input id="photo-search" class="text-input" type="search" placeholder="사진 이름 또는 아이 이름 검색" aria-label="사진 검색" value="${esc(search)}"><select id="photo-sort" aria-label="사진 정렬"><option value="newest">촬영일 최신순</option><option value="oldest">촬영일 오래된순</option><option value="name">이름순</option></select></div><div id="photo-grid" class="photo-grid"></div></section><section id="preview" class="panel preview-panel"><div class="panel-heading">선택한 사진 미리보기</div>${empty("함께 확인해 볼까요?", "사진을 선택하면 얼굴과 인식 결과를 볼 수 있어요.")}</section></div><div class="quick-links"><button data-view="children"><span>♧</span><div><b>아이 관리</b><small>아이 이름과 참고 얼굴 등록</small></div></button><button data-view="upload"><span>＋</span><div><b>사진 분류</b><small>새로운 사진과 영상 추가</small></div></button><button data-view="export"><span>⇩</span><div><b>보내기 준비</b><small>아이별 ZIP으로 내려받기</small></div></button></div>`;
  $("photo-sort").value = sort;
  renderCards();
  $("photo-search").addEventListener("input", (e) => {
    search = e.target.value;
    renderCards();
  });
  $("photo-sort").addEventListener("change", (e) => {
    sort = e.target.value;
    renderCards();
  });
}
function matchesFilter(m, id = filter) {
  return (
    id === "all" ||
    (id === "pending"
      ? !m.reviewed && m.status !== "candidate"
      : m.status === id)
  );
}
function renderCards() {
  const q = search.toLocaleLowerCase();
  const items = library.media.filter(
    (m) =>
      matchesFilter(m) &&
      `${m.name} ${[...m.children, ...m.candidates].map(childName).join(" ")}`
        .toLocaleLowerCase()
        .includes(q),
  );
  items.sort((a, b) =>
    sort === "name"
      ? a.name.localeCompare(b.name, "ko")
      : sort === "oldest"
        ? a.captured.localeCompare(b.captured)
        : b.captured.localeCompare(a.captured),
  );
  $("photo-grid").innerHTML = items.length
    ? items
        .map(
          (m) =>
            `<button class="photo-card ${m.id === selected ? "selected" : ""}" data-media="${m.id}" aria-label="${esc(m.name)} · ${esc(labels[m.status])}">${m.preview ? `<img src="${m.preview}" alt="${esc(m.name)}" loading="lazy">` : '<span class="card-placeholder">▧</span>'}<span class="card-info">${badge(m.status)}<span class="card-name">${esc(m.name)}</span><span class="card-bottom"><span>${esc(m.captured)}</span><span>${m.kind === "video" ? "영상 · " : ""}얼굴 ${m.face_count}</span></span></span></button>`,
        )
        .join("")
    : empty(
        library.media.length
          ? "검색 결과가 없어요"
          : "첫 번째 추억을 담아보세요",
        library.media.length
          ? "다른 이름이나 상태로 찾아보세요."
          : "사진을 추가하면 얼굴을 찾아 아이별로 정리할 수 있어요.",
        library.media.length
          ? ""
          : '<button class="primary" data-action="pick-files">＋ 사진·영상 추가</button>',
      );
  if (selected && items.some((m) => m.id === selected))
    run(() => selectPhoto(selected));
  else {
    selected = null;
    currentDetail = null;
    detailRequest++;
    $("preview").innerHTML =
      `<div class="panel-heading">선택한 사진 미리보기</div>${empty("함께 확인해 볼까요?", "사진을 선택하면 얼굴과 인식 결과를 볼 수 있어요.")}`;
  }
}
async function selectPhoto(id) {
  const request = ++detailRequest;
  selected = id;
  document
    .querySelectorAll("[data-media]")
    .forEach((el) => el.classList.toggle("selected", el.dataset.media === id));
  const m = await api("/api/media/" + id);
  if (request !== detailRequest || view !== "review" || !user) return;
  currentDetail = m;
  const firstFrame = m.faces[0]?.frame;
  const faces =
    m.kind === "video"
      ? m.faces.filter((f) => f.frame === firstFrame)
      : m.faces;
  const source =
    m.kind === "video" && faces.length ? faces[0].preview : m.preview;
  $("preview").innerHTML =
    `<div class="panel-heading">선택한 사진 미리보기 ${badge(m.status)}</div>${
      source
        ? `<div class="image-frame"><img src="${source}" alt="${esc(m.name)}">${faces
            .map((f) => {
              const [x1, y1, x2, y2] = f.bbox;
              return `<span class="face-box" style="left:${x1 * 100}%;top:${y1 * 100}%;width:${(x2 - x1) * 100}%;height:${(y2 - y1) * 100}%"><b>${f.candidate.child ? esc(childName(f.candidate.child)) : "확인 필요"}</b></span>`;
            })
            .join("")}</div>`
        : ""
    }<div class="preview-meta"><h3>${esc(m.name)}</h3><p>${esc(m.captured)} · ${esc(m.date_source)}${m.kind === "video" ? " · 영상은 대표 프레임으로 확인해요" : ""}</p></div><div class="face-list">${m.faces.map((f) => `<div class="face-row"><img src="${f.crop}" alt="검출된 얼굴"><div class="face-info"><b>${f.candidate.child ? esc(childName(f.candidate.child)) : "아직 이름을 몰라요"}</b><small>${f.candidate.score !== null ? "유사도 " + (f.candidate.score * 100).toFixed(1) + "% · " : ""}${esc(f.candidate.reason)}${f.frame !== null ? " · " + f.frame.toFixed(1) + "초" : ""}</small></div><button data-learn="${f.id}">참고 얼굴 등록</button></div>`).join("") || '<p class="muted">검출된 얼굴이 없어요. 직접 아이를 배정할 수 있어요.</p>'}</div><div class="preview-actions"><button class="primary" data-action="assign">아이 직접 배정</button>${m.status === "candidate" ? '<button data-action="confirm">후보대로 확인</button>' : ""}${m.reviewed ? '<button data-action="undo">확인 되돌리기</button>' : '<button data-action="exclude">정리에서 제외</button>'}</div><p class="score-note">유사도는 정확도나 확률이 아닙니다. 사진 속 아이와 후보가 일치하는지 확인해 주세요.</p>`;
}
function renderChildren() {
  $("page-content").innerHTML =
    `<section class="panel section-body"><div class="section-top"><h2>우리 아이들 <span class="blue">${library.children.length}</span></h2><button class="primary" data-action="add-child">＋ 아이 추가</button></div><p>이름을 등록한 뒤 결과 검토에서 얼굴을 골라 <b>참고 얼굴 등록</b>을 눌러주세요.<br>참고 얼굴을 추가한 뒤 다시 비교하면 사진 속 아이의 후보를 찾을 수 있어요.</p><div class="children-grid">${library.children.map((c) => `<article class="child-card"><div class="child-avatar">${esc(c.name.slice(0, 1))}</div><h3>${esc(c.name)}</h3><p>${esc(c.group_name || "그룹 미지정")} · 참고 얼굴 ${c.refs}개</p><button data-child-edit="${c.id}">이름·그룹 수정</button></article>`).join("") || empty("아이 이름부터 등록해 볼까요?", "한글 이름과 반·그룹 이름을 자유롭게 입력하세요.")}</div></section>`;
}
function childDialog(id) {
  const child = library.children.find((c) => c.id === id);
  modal(
    child ? "아이 정보 수정" : "새로운 아이 등록",
    `<form id="child-form"><label class="field-label" for="child-name">아이 이름</label><input class="text-input" id="child-name" value="${esc(child?.name || "")}" maxlength="80" required placeholder="예: 김민준" autocomplete="off"><label class="field-label" for="child-group">반·그룹 (선택)</label><input class="text-input" id="child-group" value="${esc(child?.group_name || "")}" maxlength="80" placeholder="예: 햇살반"><p class="message error modal-error" id="modal-error" hidden></p><button class="primary wide">저장하기</button></form>`,
  );
  $("child-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = e.submitter;
    button.disabled = true;
    try {
      await api("/api/children" + (child ? "/" + id : ""), {
        method: child ? "PUT" : "POST",
        body: { name: $("child-name").value, group: $("child-group").value },
      });
      closeModal();
      await refresh();
      navigate(view);
      notify("아이 정보를 저장했어요.");
    } catch (error) {
      $("modal-error").textContent = error.message;
      $("modal-error").hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  $("child-name").focus();
}
function renderUpload() {
  const tips = {
    windows: "Ctrl 또는 Shift 키로 여러 파일을 선택할 수 있어요.",
    android: "사진 선택기나 파일 앱에서 사진과 영상을 선택해 주세요.",
    iphone: "사진 보관함 또는 파일에서 선택하세요. HEIC 사진도 지원해요.",
  };
  $("page-content").innerHTML =
    `<section class="panel section-body"><h2>오늘의 순간을 추가해요</h2><p>${tips[user.platform]} 업로드한 파일은 이 서비스의 서버에서 분석·보관됩니다.</p><div class="drop-area"><span class="empty-icon">▧</span><h3>사진과 영상을 골라주세요</h3><p>JPG · PNG · HEIC · MP4 · MOV 등<br>한 번에 여러 파일 선택 · 파일당 최대 100MB</p><button id="pick-button" class="primary" data-action="pick-files" ${uploading ? "disabled" : ""}>${uploading ? "사진을 분석하고 있어요…" : "＋ 사진·영상 선택"}</button></div><ul id="upload-log" class="upload-log" aria-live="polite"></ul><div class="section-top" style="margin-top:24px;margin-bottom:0"><p class="muted" style="font-size:12px;margin:0">참고 얼굴을 새로 등록하셨나요?</p><button data-action="rematch">↻ 미확정 사진 다시 비교</button></div></section>`;
}
async function uploadFiles(files) {
  if (uploading || !files.length) return;
  uploading = true;
  navigate("upload");
  let success = 0,
    failed = 0;
  const addLog = (message) => {
    if ($("upload-log")) {
      const li = document.createElement("li");
      li.textContent = message;
      $("upload-log").append(li);
    }
  };
  for (let i = 0; i < files.length; i++) {
    if (!user) break;
    const file = files[i];
    notify(
      `${i + 1}/${files.length} · ${file.name} 분석 중이에요. 이 페이지를 열어 두세요.`,
    );
    try {
      if (file.size > 100 * 1024 * 1024)
        throw new Error("파일당 최대 100MB까지 선택할 수 있어요.");
      const data = new FormData();
      data.append("file", file);
      const result = await api("/api/media", { method: "POST", body: data });
      success++;
      addLog(
        `✓ ${file.name} — ${result.duplicate ? "이미 보관된 사진" : "분석 완료"}`,
      );
    } catch (error) {
      failed++;
      addLog(`! ${file.name} — ${error.message}`);
    }
  }
  uploading = false;
  $("file-picker").value = "";
  if (!user) return;
  await refresh();
  if ($("pick-button")) {
    $("pick-button").disabled = false;
    $("pick-button").textContent = "＋ 사진·영상 선택";
  }
  notify(
    `사진 추가를 마쳤어요. 처리 ${success}개 · 실패 ${failed}개. 결과 검토에서 확인해 주세요.`,
    failed > 0,
  );
}
function learnDialog(faceId) {
  if (!library.children.length) return childDialog();
  const face = currentDetail?.faces.find((f) => f.id === faceId);
  if (!face) return;
  modal(
    "이 얼굴은 누구인가요?",
    `<div class="face-choice"><img src="${face.crop}" alt="등록할 참고 얼굴"><p>이 얼굴과 일치하는 아이를 골라주세요.<br>다음 사진을 비교할 때 참고할 얼굴이에요.</p></div><form id="learn-form"><label class="field-label" for="learn-child">아이 선택</label><select id="learn-child">${library.children.map((c) => `<option value="${c.id}">${esc(c.name)}${c.group_name ? " · " + esc(c.group_name) : ""}</option>`).join("")}</select><p id="modal-error" class="message error modal-error" hidden></p><button class="primary wide">참고 얼굴로 등록</button></form>`,
  );
  $("learn-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    e.submitter.disabled = true;
    try {
      await api(`/api/faces/${faceId}/reference`, {
        method: "POST",
        body: { child: $("learn-child").value },
      });
      await api("/api/rematch", { method: "POST" });
      closeModal();
      await refresh();
      navigate("review");
      notify("참고 얼굴을 등록하고 미확정 사진을 다시 비교했어요.");
    } catch (error) {
      $("modal-error").textContent = error.message;
      $("modal-error").hidden = false;
      e.submitter.disabled = false;
    }
  });
}
function assignDialog() {
  if (!currentDetail) return;
  if (!library.children.length) return childDialog();
  const media = currentDetail;
  modal(
    "사진에 나온 아이 선택",
    `<p>등장한 아이를 모두 선택해 주세요. 확인한 사진만 아이별 ZIP에 포함됩니다.</p><form id="assign-form"><div class="check-list">${library.children.map((c) => `<label><input type="checkbox" name="assignment" value="${c.id}" ${media.children.includes(c.id) ? "checked" : ""}>${esc(c.name)} ${c.group_name ? "· " + esc(c.group_name) : ""}</label>`).join("")}</div><p id="modal-error" class="message error modal-error" hidden></p><button class="primary wide">선택한 아이로 검토 완료</button></form>`,
  );
  $("assign-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const children = [
      ...document.querySelectorAll('[name="assignment"]:checked'),
    ].map((c) => c.value);
    if (!children.length) {
      $("modal-error").textContent = "아이를 한 명 이상 선택하세요.";
      $("modal-error").hidden = false;
      return;
    }
    e.submitter.disabled = true;
    try {
      await api(`/api/media/${media.id}/review`, {
        method: "POST",
        body: { children },
      });
      closeModal();
      await refresh();
      navigate("review");
      notify("아이 배정을 저장했어요.");
    } catch (error) {
      $("modal-error").textContent = error.message;
      $("modal-error").hidden = false;
      e.submitter.disabled = false;
    }
  });
}
function renderExport() {
  $("page-content").innerHTML =
    `<section class="panel section-body"><h2>아이별로 추억 보내기</h2><p>검토 완료한 사진과 영상을 날짜별 폴더로 묶습니다. 원본은 그대로 보관돼요.<br>ZIP 다운로드 후 원하는 메신저나 알림장으로 직접 보내주세요.</p>${
      library.children.length
        ? `<form id="export-form"><div class="form-row"><label class="field-label">시작일<input id="export-start" class="text-input" type="date" value="${library.media.map((m) => m.captured).sort()[0] || new Date().toISOString().slice(0, 10)}" required></label><label class="field-label">종료일<input id="export-end" class="text-input" type="date" value="${
            library.media
              .map((m) => m.captured)
              .sort()
              .at(-1) || new Date().toISOString().slice(0, 10)
          }" required></label></div><div class="check-list">${library.children.map((c) => `<label><input type="checkbox" name="export-child" value="${c.id}" checked>${esc(c.name)}</label>`).join("")}</div><button class="primary" id="make-zip">⇩ 아이별 ZIP 만들기</button></form><div id="export-downloads" class="download-links"></div>`
        : empty(
            "먼저 아이를 등록해 주세요",
            "사진을 아이에게 배정하고 검토 완료하면 ZIP으로 내려받을 수 있어요.",
            '<button data-view="children">아이 관리로 이동</button>',
          )
    }</section>`;
  $("export-form")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const children = [
      ...document.querySelectorAll('[name="export-child"]:checked'),
    ].map((c) => c.value);
    if (!children.length) return notify("내려받을 아이를 선택하세요.", true);
    $("make-zip").disabled = true;
    try {
      const result = await api("/api/exports", {
        method: "POST",
        body: {
          children,
          start: $("export-start").value,
          end: $("export-end").value,
        },
      });
      $("export-downloads").innerHTML = result.exports
        .map(
          (f) =>
            `<a href="${f.url}" download>⇩ ${esc(f.name)} · ${f.count}개 파일</a>`,
        )
        .join("");
      notify(
        result.exports.length
          ? "ZIP이 준비됐어요. 아래 파일명을 눌러 내려받으세요."
          : "선택한 기간에 검토 완료한 사진이 없어요.",
      );
    } catch (error) {
      notify(error.message, true);
    } finally {
      if ($("make-zip")) $("make-zip").disabled = false;
    }
  });
}
function renderStatistics() {
  const months = {};
  for (const m of library.media.filter((m) => m.status === "confirmed"))
    months[m.captured.slice(0, 7)] = (months[m.captured.slice(0, 7)] || 0) + 1;
  const values = Object.entries(months).sort().slice(-6),
    max = Math.max(1, ...values.map((x) => x[1]));
  $("page-content").innerHTML =
    `<section class="panel section-body"><div class="section-top"><h2>아이별 사진 현황</h2><a href="/api/statistics.csv" download>⇩ CSV 내려받기</a></div><p>검토 완료한 사진과 영상만 집계됩니다. 단체 사진은 등장한 아이 각각의 수에 포함돼요.</p>${values.length ? `<div class="inline-chart" aria-label="월별 검토 완료 자료 수">${values.map(([month, count]) => `<div class="chart-column"><b>${count}</b><i style="height:${(count / max) * 100}px"></i><span>${month}</span></div>`).join("")}</div>` : ""}<div class="table-wrap"><table class="data-table"><thead><tr><th>아이 이름</th><th>반·그룹</th><th>사진</th><th>영상</th><th>합계</th></tr></thead><tbody>${library.statistics.map((c) => `<tr><td>${esc(c.name)}</td><td>${esc(c.group_name || "—")}</td><td>${c.photos}</td><td>${c.videos}</td><td>${c.photos + c.videos}</td></tr>`).join("") || '<tr><td colspan="5">등록한 아이가 없습니다.</td></tr>'}</tbody></table></div></section>`;
}
function guide() {
  modal(
    "PhotoJoy 사용 가이드",
    `<p>사진 속 소중한 순간을 아이별로 모으는 방법이에요.</p><ol><li><b>로그인:</b> 접속 환경을 선택하고 아이디로 로그인하세요. 처음이라면 계정을 만들어요. Google 로그인은 운영자가 연결한 서비스에서 사용할 수 있어요.</li><li><b>아이 관리:</b> 아이 이름과 반·그룹을 등록해요. 한글을 그대로 입력할 수 있어요.</li><li><b>사진 분류:</b> 기기의 사진과 영상을 선택해요. 서비스 서버에서 얼굴을 분석하고 계정별로 보관해요.</li><li><b>참고 얼굴:</b> 결과 검토에서 사진을 선택하고 각 얼굴 옆의 참고 얼굴 등록을 눌러 아이를 연결해요. 미확정 사진을 다시 비교해요.</li><li><b>결과 검토:</b> 후보대로 확인하거나 아이 직접 배정으로 등장한 아이를 모두 선택해요. 확인 되돌리기도 가능해요.</li><li><b>보내기 준비:</b> 기간과 아이를 선택해 ZIP을 만들고 내려받아요. 통계는 CSV로 저장할 수 있어요.</li></ol><h3>기기별 이용</h3><p>윈도우는 여러 파일을 Ctrl/Shift로 선택할 수 있어요. 안드로이드·아이폰은 사진 선택기나 파일 앱을 이용해 주세요. 모바일에서는 화면이 세로로 배치됩니다. 접속 환경 선택은 안내와 세션에 저장되며 운영체제를 변경하지 않습니다.</p><h3>사진 인식 결과</h3><p>자동 승인 후보는 확정 결과가 아닙니다. 형제나 가려진 얼굴은 잘못 인식될 수 있어요. 영상은 최대 8개 프레임을 분석합니다.</p>`,
  );
}
function privacy() {
  modal(
    "사진 보관 안내",
    "<p>웹 버전에서 선택한 사진과 영상은 PhotoJoy 서비스 서버로 업로드됩니다. 원본, 미리보기와 얼굴 특징은 로그인한 계정별 공간에 보관됩니다.</p><p>얼굴 인식은 서버의 OpenCV 모델로 실행하며 Google 로그인에 사진을 보내지 않습니다. Google은 계정 인증에만 사용됩니다.</p><p>기기의 원본은 변경하거나 삭제하지 않습니다. 공유 기기에서는 사용을 마친 뒤 로그아웃해 주세요. 서버 운영자는 서버의 저장 자료에 접근할 수 있으므로 신뢰할 수 있는 운영자가 제공한 서비스에서 사용하세요.</p>",
  );
}

document.addEventListener("click", (e) => {
  const target = e.target.closest("button");
  if (!target) return;
  if (target.dataset.view) return navigate(target.dataset.view);
  if (target.dataset.filter) {
    filter = target.dataset.filter;
    renderReview();
    return;
  }
  if (target.dataset.media) return run(() => selectPhoto(target.dataset.media));
  if (target.dataset.childEdit) return childDialog(target.dataset.childEdit);
  if (target.dataset.learn) return learnDialog(target.dataset.learn);
  const action = target.dataset.action;
  if (!action) return;
  if (action === "guide") return guide();
  if (action === "privacy") return privacy();
  if (action === "add-child") return childDialog();
  if (action === "assign") return assignDialog();
  if (action === "pick-files") {
    if (!uploading) $("file-picker").click();
    return;
  }
  run(async () => {
    target.disabled = true;
    try {
      if (action === "rematch") {
        await api("/api/rematch", { method: "POST" });
        await refresh();
        navigate("review");
        notify("미확정 사진을 다시 비교했어요.");
        return;
      }
      if (!currentDetail) return;
      const id = currentDetail.id;
      if (action === "exclude")
        await api(`/api/media/${id}/review`, {
          method: "POST",
          body: { children: [], excluded: true },
        });
      if (action === "confirm" || action === "undo")
        await api(`/api/media/${id}/${action}`, { method: "POST" });
      await refresh();
      navigate("review");
      notify("검토 결과를 저장했어요.");
    } finally {
      target.disabled = false;
    }
  });
});
$("close-modal").addEventListener("click", closeModal);
$("modal").addEventListener("click", (e) => {
  if (e.target === $("modal")) {
    const rect = $("modal").getBoundingClientRect();
    if (
      e.clientX < rect.left ||
      e.clientX > rect.right ||
      e.clientY < rect.top ||
      e.clientY > rect.bottom
    )
      closeModal();
  }
});
$("login-tab").addEventListener("click", () => mode("login"));
$("register-tab").addEventListener("click", () => mode("register"));
$("show-password").addEventListener("click", () => {
  const show = $("password").type === "password";
  $("password").type = show ? "text" : "password";
  $("show-password").textContent = show ? "숨기기" : "보기";
  $("show-password").setAttribute("aria-pressed", String(show));
  $("show-password").setAttribute(
    "aria-label",
    show ? "비밀번호 숨기기" : "비밀번호 표시",
  );
});
$("auth-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("auth-submit").disabled = true;
  $("auth-error").hidden = true;
  try {
    await enter(
      await api("/api/auth/" + authMode, {
        method: "POST",
        body: {
          username: $("username").value,
          password: $("password").value,
          platform: platform(),
        },
      }),
    );
  } catch (error) {
    authError(error.message);
  } finally {
    $("auth-submit").disabled = false;
  }
});
$("logout").addEventListener("click", () =>
  run(async () => {
    if (uploading) {
      notify("업로드가 끝난 뒤 로그아웃해 주세요.");
      return;
    }
    await api("/api/auth/logout", { method: "POST" });
    user = null;
    showLogin();
    await setupGoogle();
  }),
);
$("file-picker").addEventListener("change", (e) =>
  run(() => uploadFiles([...e.target.files])),
);
document.addEventListener("keydown", (e) => {
  if (e.key === "F1") {
    e.preventDefault();
    guide();
  }
});

async function setupGoogle() {
  config = await api("/api/config");
  $("register-tab").hidden = !config.registration;
  if (!config.google_client_id) {
    $("google-state").textContent =
      "Google 로그인 준비 중 · 지금은 아이디로 이용할 수 있어요.";
    return;
  }
  $("google-state").textContent =
    "Google 계정으로 간편하게 로그인할 수 있어요.";
  try {
    if (!window.google?.accounts?.id)
      await new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = "https://accounts.google.com/gsi/client";
        script.async = true;
        script.onload = resolve;
        script.onerror = reject;
        document.head.append(script);
      });
    google.accounts.id.initialize({
      client_id: config.google_client_id,
      nonce: config.google_nonce,
      auto_select: false,
      callback: async (result) => {
        try {
          await enter(
            await api("/api/auth/google", {
              method: "POST",
              body: { credential: result.credential, platform: platform() },
            }),
          );
        } catch (error) {
          authError(error.message);
          await setupGoogle();
        }
      },
    });
    $("google-button").replaceChildren();
    google.accounts.id.renderButton($("google-button"), {
      type: "standard",
      theme: "outline",
      size: "large",
      text: "continue_with",
      shape: "rectangular",
      width: Math.min(360, $("auth-form").clientWidth),
      locale: "ko",
    });
  } catch {
    $("google-state").textContent =
      "Google 로그인을 불러오지 못했어요. 아이디로 로그인하거나 새로고침해 주세요.";
  }
}
async function boot() {
  const agent = navigator.userAgent;
  const guess = /Android/i.test(agent)
    ? "android"
    : /iPhone|iPad|iPod/i.test(agent)
      ? "iphone"
      : "windows";
  document.querySelector(`input[name="platform"][value="${guess}"]`).checked =
    true;
  try {
    await setupGoogle();
  } catch {
    authError(
      "서버에 연결할 수 없어요. 서비스 주소를 확인하거나 잠시 후 다시 열어주세요.",
    );
    $("auth-submit").disabled = true;
    $("google-state").textContent = "서버 연결을 기다리고 있어요.";
    return;
  }
  try {
    await enter(await api("/api/auth/me"));
  } catch {
    showLogin();
  }
}
boot();
