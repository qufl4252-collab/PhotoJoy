import {
  authReady,
  getSession,
  getVault,
  login,
  logout,
  signInGoogle,
  resetPassword,
  onAccountChanged,
} from "./auth.js";
import { Project } from "./project.js";
import { analyzeFile, captureDate } from "./media-adapter.js";
import { STATES, calibration } from "./classification.js";
import { statistics, makeExports, csv } from "./export.js";
import { importPortable } from "./portable.js";
const $ = (id) => document.getElementById(id),
  esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const platform = () => document.querySelector("[name=platform]:checked").value;
let project,
  user,
  data,
  view = "auto",
  authMode = "login",
  selected = new Set(),
  galleryChild = null,
  page = 0,
  renderId = 0,
  referenceChild = null,
  enqueuing = false;
const urls = new Map(),
  titles = {
    auto: "사진 자동 분류",
    review: "확인 필요",
    children: "아이 관리",
    export: "학부모 보내기",
    statistics: "통계",
    settings: "설정",
  };
function notify(text, error = false) {
  $("notice").textContent = text;
  $("notice").hidden = false;
  $("notice").className = "message" + (error ? " error" : "");
}
function authError(text) {
  $("auth-error").textContent = text;
  $("auth-error").hidden = false;
}
function run(fn) {
  return Promise.resolve()
    .then(fn)
    .catch((e) => notify(e.message, true));
}
function modal(title, content) {
  $("modal-title").textContent = title;
  $("modal-content").innerHTML = content;
  if (!$("modal").open) $("modal").showModal();
}
function closeModal() {
  $("modal").close();
}
function badge(state) {
  return `<span class="badge ${state === "organized" ? "confirmed" : state === "failed" ? "error" : state === "review" ? "review" : "candidate"}">${esc(STATES[state] || state)}</span>`;
}
const name = (id) => data.kids.find((c) => c.id === id)?.name || "미등록";
async function blobURL(table, id) {
  if (!id) return "";
  const key = `${project.v.owner}:${table}:${id}`;
  if (!urls.has(key)) {
    const blob = await project.v.get(table, id);
    if (!blob) return "";
    urls.set(key, URL.createObjectURL(blob));
  }
  return urls.get(key);
}
function release() {
  for (const url of urls.values()) URL.revokeObjectURL(url);
  urls.clear();
}
async function enter(result) {
  user = result.user;
  project = await new Project(getVault(), analyzeFile, captureDate).init();
  project.change = refresh;
  $("login-screen").hidden = true;
  $("workspace").hidden = false;
  $("password").value = "";
  $("user-label").textContent = user.display_name + "님";
  $("platform-label").textContent =
    { windows: "윈도우", android: "안드로이드", iphone: "아이폰" }[
      user.platform
    ] + " · 이 브라우저에 보관";
  await refresh();
  navigate("auto");
}
function showLogin() {
  project?.pause();
  project = null;
  user = null;
  data = null;
  release();
  renderId++;
  $("workspace").hidden = true;
  $("login-screen").hidden = false;
  $("page-content").replaceChildren();
  $("password").value = "";
  closeModal();
}
async function refresh() {
  if (!project) return;
  const p = project,
    next = await p.snapshot();
  if (project !== p) return;
  data = next;
  const c = data.counts;
  $("total-count").textContent = c.total + "개";
  $("child-count").textContent = data.kids.length + "명";
  $("confirmed-count").textContent = c.organized + "개";
  $("review-progress").value = c.total ? (c.organized / c.total) * 100 : 0;
  $("summary-copy").textContent =
    `정리 완료 ${c.organized} · 확인 필요 ${c.review} · 대기/분석 ${c.queued + c.analyzing + c.classified} · 실패 ${c.failed} · 제외 ${c.excluded}`;
  if (!$("modal").open && (view === "auto" || view === "review"))
    await render();
}
function navigate(next) {
  view = next;
  page = 0;
  galleryChild = null;
  selected.clear();
  $("notice").hidden = true;
  render();
}
async function render() {
  if (!data) return;
  const ticket = ++renderId;
  $("page-title").textContent = titles[view];
  $("page-description").textContent = {
    auto: "사진을 추가하고 시작을 누르면, 아이별 정리까지 이어집니다.",
    review: "어려운 얼굴만 확인하세요. 확실한 아이의 사진은 이미 정리됩니다.",
    children: "아이별로 선명한 참고 얼굴 3~5장을 등록해 주세요.",
    export: "자동 정리된 사진을 날짜별 ZIP으로 준비하세요.",
    statistics: "같은 정리 결과에서 집계한 아이별 사진 현황입니다.",
    settings: "인식 기준, 정리 방식, 복원과 작업 기록을 관리하세요.",
  }[view];
  document
    .querySelectorAll("[data-view]")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  const html = await {
    auto: renderAuto,
    review: renderReview,
    children: renderChildren,
    export: renderExport,
    statistics: renderStatistics,
    settings: renderSettings,
  }[view]();
  if (ticket === renderId) $("page-content").innerHTML = html;
}
function renderAuto() {
  const c = data.jobCounts,
    waiting = data.jobs.some((j) => j.state === "queued");
  return `<section class="panel section-body"><div class="section-top"><div><h2>한 번 시작하면, 정리까지</h2><p>① 아이·참고 얼굴 등록 → ② 사진 추가 → ③ 자동 분류 시작</p></div><button data-view="children">아이·참고 얼굴 등록</button></div><div class="pipeline-actions"><button data-action="pick" ${enqueuing ? "disabled" : ""}>＋ 사진·동영상 추가</button><button data-action="folder" ${enqueuing ? "disabled" : ""}>▱ 폴더에서 일괄 가져오기</button><button class="primary" data-action="start" ${project.running || enqueuing || !waiting ? "disabled" : ""}>${project.running ? "분류 진행 중…" : "✦ 자동 분류 시작"}</button><button data-action="pause" ${project.running ? "" : "disabled"}>현재 파일 후 일시정지</button></div><p class="muted">브라우저 안에서 분석합니다. 작업 중 탭을 열어 두세요. 닫힌 작업은 다시 로그인한 뒤 시작할 수 있습니다. JPG·PNG·WebP 및 HEIC 사진·브라우저가 재생 가능한 MOV 등, 파일당 100MB.</p><div class="queue-progress"><b>${c.finished.toLocaleString()} / ${c.total.toLocaleString()}개 처리</b><progress max="${c.total || 1}" value="${c.finished}"></progress></div><div class="status-grid">${Object.entries(
    STATES,
  )
    .map(([s, l]) => `<div><small>${l}</small><strong>${c[s]}</strong></div>`)
    .join(
      "",
    )}</div><p class="input-help">작업 숫자는 가져오기·재분석 시도 전체 기록입니다. 상단은 중복을 뺀 보관 파일 수입니다. 일부 얼굴이 보류인 사진도 확실한 아이의 목록에 포함됩니다.</p>${!data.refs.length ? '<p class="message">참고 얼굴이 없습니다. 아이 관리에서 먼저 등록해 주세요.</p>' : ""}<details><summary>최근 작업 ${Math.min(30, data.jobs.length)}개</summary><div class="job-list">${[
    ...data.jobs,
  ]
    .reverse()
    .slice(0, 30)
    .map(
      (j) =>
        `<div>${badge(j.state)} <span>${esc(j.name)}</span><small>${esc(j.error || "")}</small></div>`,
    )
    .join(
      "",
    )}</div></details></section><section class="panel section-body"><h2>아이별 정리 결과</h2><div class="children-grid">${
    statistics(data.kids, data.media)
      .map(
        (c) =>
          `<button class="child-card" data-gallery="${c.id}"><div class="child-avatar">${esc(c.name[0])}</div><h3>${esc(c.name)}</h3><p>${c.total}개 · ${esc(c.group_name)}</p><small>자동·교정 결과 보기 →</small></button>`,
      )
      .join("") || "<p>아이 이름과 참고 얼굴을 등록해 주세요.</p>"
  }</div></section>`;
}
function reviewItems() {
  return data.media.filter((m) =>
    galleryChild
      ? m.children.includes(galleryChild)
      : m.needsReview || m.state === "failed",
  );
}
async function cards(items) {
  return `<div class="photo-grid">${(await Promise.all(items.slice(page * 48, (page + 1) * 48).map(async (m) => `<article class="photo-card ${selected.has(m.id) ? "selected" : ""}"><label class="card-check"><input type="checkbox" data-select="${m.id}" ${selected.has(m.id) ? "checked" : ""} aria-label="${esc(m.name)} 선택"></label><button class="photo-open" data-photo="${m.id}">${m.previewId ? `<img loading="lazy" src="${await blobURL("previews", m.previewId)}" alt="${esc(m.name)}">` : '<span class="empty-icon">▧</span>'}<div class="photo-card-info">${badge(m.state)}<strong>${esc(m.name)}</strong><small>${esc(m.captured)} · 얼굴 ${m.faces.length}개</small><small>${m.children.map((id) => esc(name(id))).join(", ") || "배정 없음"}${m.needsReview ? " · 확인 필요" : ""}</small></div></button></article>`))).join("")}</div><div class="pipeline-actions"><button data-action="prev-page" ${page === 0 ? "disabled" : ""}>이전</button><span>${page + 1} / ${Math.max(1, Math.ceil(items.length / 48))}</span><button data-action="next-page" ${(page + 1) * 48 >= items.length ? "disabled" : ""}>다음</button></div>`;
}
async function renderReview() {
  const items = reviewItems(),
    valid = new Set(items.map((m) => m.id));
  selected = new Set([...selected].filter((id) => valid.has(id)));
  return `<section class="panel section-body"><div class="section-top"><h2>${galleryChild ? esc(name(galleryChild)) + " 정리 결과" : "확인 필요"} <span class="blue">${items.length}</span></h2><button data-action="rematch" ${project.running ? "disabled" : ""}>참고 얼굴로 다시 비교</button></div><div class="batch-bar"><button data-action="select-visible">이 페이지 모두 선택</button><button data-action="clear-selection">선택 해제</button><span id="selected-count">${selected.size}개 선택</span><button data-action="batch-assign">아이 일괄 배정</button><button data-action="batch-exclude">선택 제외</button><button data-action="reanalyze">선택 재분석</button><button data-action="trash">휴지통 이동</button></div>${items.length ? await cards(items) : '<div class="empty"><h3>확인할 사진이 없습니다.</h3><p>확실한 결과는 자동으로 정리됩니다.</p></div>'}</section>`;
}
async function openPhoto(id) {
  const m = await project.v.get("media", id);
  if (!m) return;
  const first = m.faces[0],
    preview = await blobURL("previews", first?.previewId || m.previewId);
  modal(
    m.name,
    `<div class="large-preview">${
      preview
        ? `<div class="image-frame"><img src="${preview}" alt="${esc(m.name)}">${m.faces
            .filter((f) => f.frame === first?.frame)
            .map((f) => {
              const [x, y, r, b] = f.bbox;
              return `<span class="face-box" style="left:${x * 100}%;top:${y * 100}%;width:${(r - x) * 100}%;height:${(b - y) * 100}%"><b>${esc(f.manualChild ? name(f.manualChild) : f.candidate?.accepted ? name(f.candidate.child) : "미확정")}</b></span>`;
            })
            .join("")}</div>`
        : "<p>미리보기를 만들지 못했습니다. 원본은 보관되어 있습니다.</p>"
    }</div><p>${badge(m.state)} ${esc(m.captured)} · ${esc(m.date_source)} · ${esc(m.error || m.reason || "")}</p><p>정리된 아이: ${m.children.map((id) => esc(name(id))).join(", ") || "없음"}</p><div class="face-list">${(await Promise.all(m.faces.map(async (f) => `<div class="face-row correction-row"><img src="${await blobURL("crops", f.id)}" alt="검출 얼굴"><div class="face-info"><b>${f.candidate?.accepted ? esc(name(f.candidate.child)) : "확인 필요 / 미등록"}</b><small>비교 점수 ${f.candidate?.score == null ? "없음" : f.candidate.score.toFixed(3)} · 차순위 ${f.candidate?.runner_up?.toFixed(3) || "없음"}</small><small>${esc(f.candidate?.reason || f.embeddingError)} ${f.frame != null ? "· " + f.frame.toFixed(1) + "초" : ""}</small><label>실제 인물<select id="face-child-${f.id}"><option value="">미등록 인물 / 제외</option>${data.kids.map((k) => `<option value="${k.id}" ${k.id === (f.manualChild || f.candidate?.child) ? "selected" : ""}>${esc(k.name)}</option>`).join("")}</select></label><label><input id="face-learn-${f.id}" type="checkbox" ${f.quality?.referenceUsable === false ? "disabled" : ""}>확인한 얼굴을 참고 데이터에 반영</label></div><button data-correct="${f.id}" data-media-id="${m.id}">얼굴 교정 저장</button><button data-new-from-face="${f.id}" data-media-id="${m.id}">새 아이로 등록</button></div>`))).join("")}</div><div class="pipeline-actions"><button data-assign-one="${m.id}">사진 전체 아이 배정</button><button data-undo="${m.id}">이전 변경 되돌리기</button><button data-reanalyze-one="${m.id}">원본 재분석</button><button data-original="${m.id}">원본 다운로드</button></div><details><summary>검출·인식 진단 및 정리 경로</summary><pre>${esc(JSON.stringify({ diagnostics: m.diagnostics, policy: m.policy, paths: m.paths }, null, 2))}</pre></details><p class="score-note">비교 점수는 신원 일치 확률이 아닙니다. 사진 전체 배정은 참고 얼굴을 자동 학습하지 않습니다.</p>`,
  );
}
function renderChildren() {
  return `<section class="panel section-body"><div class="section-top"><h2>아이와 참고 얼굴</h2><button class="primary" data-action="add-child">＋ 아이 등록</button></div><p>정면·다른 각도의 선명한 사진 3~5장을 권장합니다. 여러 얼굴이 나오면 학습할 얼굴을 직접 고릅니다.</p><div class="children-grid">${data.kids
    .map((k) => {
      const refs = data.refs.filter((r) => r.child === k.id),
        n = data.media.filter((m) => m.children.includes(k.id)).length;
      return `<article class="child-card"><div class="child-avatar">${esc(k.name[0])}</div><h3>${esc(k.name)}</h3><p>${esc(k.group_name || "그룹 미지정")}</p><p>참고 ${refs.length}장 · <b>${refs.length >= 3 ? "정상" : refs.length ? "부족" : "미학습"}</b> · 분류 ${n}개</p><button data-reference="${k.id}">참고 사진 추가</button><button data-manage-refs="${k.id}">참고 얼굴 관리</button><button data-child-edit="${k.id}">이름·반 수정</button></article>`;
    })
    .join("")}</div></section>`;
}
function childDialog(id, fromFace) {
  const k = data.kids.find((c) => c.id === id);
  modal(
    k ? "아이 정보 수정" : "아이 등록",
    `<form id="child-form" data-child="${id || ""}" ${fromFace ? `data-from-media="${fromFace.media}" data-from-face="${fromFace.face}"` : ""}><label class="field-label" for="child-name">아이 이름</label><input class="text-input" id="child-name" value="${esc(k?.name || "")}" maxlength="80" required><label class="field-label" for="child-group">반·그룹</label><input class="text-input" id="child-group" value="${esc(k?.group_name || "")}" maxlength="80"><p id="modal-error" role="alert"></p><button class="primary wide">${k ? "저장하기" : "저장하고 참고 얼굴 등록"}</button></form>`,
  );
  $("child-name").focus();
}
async function manageRefs(child) {
  const refs = data.refs.filter((r) => r.child === child);
  modal(
    name(child) + " 참고 얼굴",
    `<p>제외한 참고 얼굴은 백업에서 복원할 수 있습니다. 교체하려면 기존 얼굴을 제외하고 새 사진을 추가하세요.</p><button data-reference="${child}">사진 추가</button><button data-rebuild="${child}">원본에서 특징 재추출</button><div class="reference-grid">${(await Promise.all(refs.map(async (r) => `<article><img src="${await blobURL("crops", r.cropId || r.faceId || r.id.split(":")[0])}" alt="참고 얼굴"><p>${esc(r.origin)}</p><button data-remove-ref="${esc(r.id)}">참고에서 제외</button></article>`))).join("")}</div>`,
  );
}
async function registerReferences(files) {
  const child = referenceChild;
  closeModal();
  let added = 0,
    failed = 0;
  for (const file of files) {
    notify(`${name(child)} · ${file.name} 참고 얼굴 분석 중…`);
    try {
      const analysis = await analyzeFile(file, await project.settings());
      if (!analysis.faces.length) throw new Error("얼굴을 찾지 못했습니다.");
      const index = await new Promise((resolve) => {
        modal(
          "학습할 얼굴 확인",
          `<p>${esc(file.name)} · ${analysis.faces.length}개 얼굴. 이 아이의 얼굴 하나를 선택하세요.</p><div id="reference-choices" class="reference-grid"></div><button id="skip-reference">이 사진 건너뛰기</button>`,
        );
        const temp = [];
        const done = (value) => {
            for (const url of temp) URL.revokeObjectURL(url);
            $("modal").removeEventListener("close", closed);
            resolve(value);
          },
          closed = () => done(null);
        for (let i = 0; i < analysis.faces.length; i++) {
          const f = analysis.faces[i],
            blob = analysis.entries.find(
              (e) => e.table === "crops" && e.id === f.id,
            ).value,
            url = URL.createObjectURL(blob),
            b = document.createElement("button");
          temp.push(url);
          b.innerHTML = `<img src="${url}" alt="참고 얼굴 ${i + 1}"><span>${f.quality?.referenceUsable === false ? "품질 부족" : "이 얼굴 선택"}</span>`;
          b.disabled = f.quality?.referenceUsable === false;
          b.onclick = () => done(i);
          $("reference-choices").append(b);
        }
        $("skip-reference").onclick = () => done(null);
        $("modal").addEventListener("close", closed, { once: true });
      });
      closeModal();
      if (index !== null) {
        await project.addReference(child, file, analysis, index);
        added++;
      }
    } catch (error) {
      failed++;
      notify(`${file.name}: ${error.message}`, true);
    }
  }
  await refresh();
  await render();
  notify(
    `참고 얼굴 ${added}개 등록 · 실패 ${failed}개. 기존 미확정 결과에도 반영했습니다.`,
    failed > 0,
  );
}
function assignmentDialog(ids) {
  if (!ids.length) throw new Error("사진을 선택해 주세요.");
  modal(
    `${ids.length}개 사진에 아이 배정`,
    `<form id="assignment-form" data-ids="${ids.join(",")}"><p>선택한 아이 모두에게 배정하며 기존 배정을 교체합니다. 얼굴 학습은 하지 않습니다.</p><div class="check-list">${data.kids.map((k) => `<label><input type="checkbox" name="assignment" value="${k.id}">${esc(k.name)}</label>`).join("")}</div><p id="modal-error" role="alert"></p><button class="primary wide">선택한 아이로 정리 완료</button></form>`,
  );
}
async function renderExport() {
  const records = (await project.v.all("exports")).sort(
    (a, b) => b.created - a.created,
  );
  return `<section class="panel section-body"><h2>자동 정리 결과 보내기</h2><p>확실하게 인식되거나 교정된 사진을 바로 준비합니다. 전체 ZIP에는 보류 폴더와 분류기록도 포함합니다. 큰 결과는 약 64MB 단위로 나눕니다.</p><form id="export-form"><div class="form-row"><label>시작일<input class="text-input" id="export-start" type="date" value="${data.media.map((m) => m.captured).sort()[0] || new Date().toISOString().slice(0, 10)}" required></label><label>종료일<input class="text-input" id="export-end" type="date" value="${
    data.media
      .map((m) => m.captured)
      .sort()
      .at(-1) || new Date().toISOString().slice(0, 10)
  }" required></label></div><div class="check-list">${data.kids.map((k) => `<label><input name="export-child" type="checkbox" value="${k.id}" checked>${esc(k.name)}</label>`).join("")}</div><button class="primary" name="mode" value="child">아이별 ZIP 준비</button> <button name="mode" value="all">전체 ZIP 준비</button></form><div class="export-history">${records.map((r) => `<div><b>${esc(r.name)}</b><small>${r.count}개 파일 · ${r.sentAt ? "사용자가 발송 완료 표시함" : "전송 준비 — 아직 발송하지 않음"}</small><button data-download="${r.id}">ZIP 다운로드</button><button data-sent="${r.id}" ${r.sentAt ? "disabled" : ""}>직접 발송했음 표시</button></div>`).join("")}</div></section>`;
}
function renderStatistics() {
  const rows = statistics(data.kids, data.media);
  return `<section class="panel section-body"><div class="section-top"><h2>아이별 정리 통계</h2><button data-action="csv">CSV 내려받기</button></div><p>다중 인물 사진은 각 아이에게 한 번씩 집계합니다. 제외·휴지통은 포함하지 않습니다.</p><div class="table-wrap"><table class="data-table"><thead><tr><th>이름</th><th>반</th><th>사진</th><th>영상</th><th>합계</th></tr></thead><tbody>${rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.group_name)}</td><td>${r.photos}</td><td>${r.videos}</td><td>${r.total}</td></tr>`).join("")}</tbody></table></div></section>`;
}
async function renderSettings() {
  const s = data.settings,
    p = calibration(await project.gallery(), s.sensitivity),
    backups = (await project.v.all("backups")).sort(
      (a, b) => b.created - a.created,
    ),
    trash = (await project.v.all("media")).filter((m) => m.deletedAt);
  return `<section class="panel section-body"><h2>분류와 정리 설정</h2><form id="settings-form"><div class="form-row"><label>인식 민감도<select id="sensitivity">${[
    ["bold", "과감"],
    ["balanced", "기본"],
    ["careful", "신중"],
  ]
    .map(
      ([v, n]) =>
        `<option value="${v}" ${s.sensitivity === v ? "selected" : ""}>${n}</option>`,
    )
    .join(
      "",
    )}</select></label><label>폴더 정리<select id="unit"><option value="week" ${s.unit === "week" ? "selected" : ""}>주차별 (1~7일이 1주차)</option><option value="day" ${s.unit === "day" ? "selected" : ""}>일별</option></select></label></div><div class="form-row"><label>최소 얼굴 크기 (분석 이미지 px)<input class="text-input" id="min-pixels" type="number" min="16" max="200" value="${s.minFacePixels}"></label><label>작은 얼굴 제외 (가장 큰 얼굴 대비, 0은 제외 안 함)<input class="text-input" id="min-relative" type="number" min="0" max="0.9" step="0.05" value="${s.minRelative}"></label></div><p>${esc(p.note)} 점수 기준 ${p.threshold.toFixed(3)}, 후보 차이 ${p.margin.toFixed(3)}. ${p.calibrated ? `참고 얼굴 내 통과율 ${(p.referenceRecall * 100).toFixed(1)}% (현장 정확도 아님).` : ""}</p><button class="primary">저장하고 미확정 결과 다시 비교</button></form></section><section class="panel section-body"><h2>저장·복원</h2><p>사진과 얼굴 특징은 이 브라우저의 계정별 IndexedDB에만 보관됩니다. Firebase에는 로그인 계정만 보관합니다. 다른 기기로 동기화되지 않습니다. 사이트 데이터 삭제 시 자료가 사라지므로 원본과 ZIP을 별도로 보관하세요. 휴지통은 자동 삭제하지 않습니다.</p><button data-action="backup">변경 전 상태 백업</button> <button data-action="import-portable">기존 PhotoJoy 자료 가져오기</button><p class="input-help">기존 서버 자료는 PhotoJoy-기존자료 ZIP 분할본을 모두 선택하세요. 브라우저 안에서만 읽습니다.</p><details><summary>상태 백업 ${backups.length}개</summary>${backups
    .slice(0, 20)
    .map(
      (b) =>
        `<p>${esc(new Date(b.created).toLocaleString())} · ${esc(b.reason)} <button data-restore="${b.id}">이 상태로 복원</button></p>`,
    )
    .join(
      "",
    )}<p>백업은 배정·참고 얼굴·작업 기록을 복원하며, 브라우저 삭제에 대비한 외부 백업은 아닙니다.</p></details><details><summary>휴지통 ${trash.length}개 (원본·관련 자료 보존)</summary>${trash.map((m) => `<p>${esc(m.name)} <button data-trash-restore="${m.id}">복원</button></p>`).join("")}</details></section><section class="panel section-body"><h2>최근 분류·교정 기록</h2><div class="job-list">${data.media
    .flatMap((m) => (m.history || []).map((h) => ({ ...h, name: m.name })))
    .sort((a, b) => b.created - a.created)
    .slice(0, 80)
    .map(
      (h) =>
        `<p>${esc(h.name)} · ${esc(h.reason || "기존 교정")} · ${esc(new Date(h.created || 0).toLocaleString())}</p>`,
    )
    .join("")}</div></section>`;
}
function download(blob, filename) {
  const url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}
function guide() {
  modal(
    "PhotoJoy 사용 가이드",
    "<ol><li>아이 관리에서 한글 이름·반과 참고 얼굴 3~5장을 등록합니다.</li><li>사진 자동 분류에서 파일 또는 폴더를 추가하고 자동 분류 시작을 누릅니다.</li><li>확실한 아이는 즉시 정리됩니다. 불확실한 얼굴만 확인 필요에서 교정하며 여러 사진은 일괄 배정할 수 있습니다.</li><li>얼굴별 교정에서 참고 데이터 반영을 직접 선택하면 다음 비교에 사용합니다. 자동 추측은 학습하지 않습니다.</li><li>학부모 보내기에서 아이별/전체 ZIP을 내려받습니다. 실제 발송 후 직접 발송했음을 표시합니다.</li><li>설정에서 민감도, 일별·주차별 정리, 백업 복원, 휴지통을 관리합니다.</li></ol><p>사진은 현재 브라우저에 보관됩니다. 분석 중 탭을 열어 두세요. 영상은 최대 8프레임을 분석합니다. HEIC·MOV 지원은 브라우저 코덱에 따라 다르며 실패한 파일도 원본을 보관합니다.</p>",
  );
}
document.addEventListener("click", (event) => {
  const b = event.target.closest("button");
  if (!b || b.disabled) return;
  if (b.dataset.view) return navigate(b.dataset.view);
  run(async () => {
    if (b.dataset.gallery) {
      view = "review";
      galleryChild = b.dataset.gallery;
      selected.clear();
      page = 0;
      return render();
    }
    if (b.dataset.photo) return openPhoto(b.dataset.photo);
    if (b.dataset.childEdit) return childDialog(b.dataset.childEdit);
    if (b.dataset.reference) {
      referenceChild = b.dataset.reference;
      $("reference-picker").click();
      return;
    }
    if (b.dataset.manageRefs) return manageRefs(b.dataset.manageRefs);
    if (b.dataset.removeRef) {
      await project.retireReference(b.dataset.removeRef);
      closeModal();
      await refresh();
      return render();
    }
    if (b.dataset.rebuild) {
      b.disabled = true;
      const r = await project.rebuildReferences(b.dataset.rebuild);
      closeModal();
      await refresh();
      notify(`${r.rebuilt}개 재추출. ${r.errors.join(" ")}`);
      return render();
    }
    if (b.dataset.correct) {
      await project.correctFace(
        b.dataset.mediaId,
        b.dataset.correct,
        $("face-child-" + b.dataset.correct).value,
        $("face-learn-" + b.dataset.correct).checked,
      );
      closeModal();
      await refresh();
      return render();
    }
    if (b.dataset.newFromFace)
      return childDialog(null, {
        media: b.dataset.mediaId,
        face: b.dataset.newFromFace,
      });
    if (b.dataset.assignOne) return assignmentDialog([b.dataset.assignOne]);
    if (b.dataset.undo) {
      await project.undo(b.dataset.undo);
      closeModal();
      await refresh();
      return render();
    }
    if (b.dataset.reanalyzeOne) {
      closeModal();
      return project.reanalyze([b.dataset.reanalyzeOne]);
    }
    if (b.dataset.original) {
      const m = await project.v.get("media", b.dataset.original);
      return download(await project.v.get("originals", m.id), m.name);
    }
    if (b.dataset.download) {
      const r = await project.v.get("exports", b.dataset.download);
      return download(await project.v.get("exportBlobs", r.id), r.name);
    }
    if (b.dataset.sent) {
      const r = await project.v.get("exports", b.dataset.sent);
      r.sentAt = Date.now();
      await project.v.put("exports", r.id, r);
      return render();
    }
    if (b.dataset.restore) {
      if (confirm("현재 상태를 백업한 뒤 선택한 시점으로 복원할까요?")) {
        await project.restore(b.dataset.restore);
        await refresh();
        await render();
      }
      return;
    }
    if (b.dataset.trashRestore) {
      await project.restoreTrash(b.dataset.trashRestore);
      await refresh();
      return render();
    }
    switch (b.dataset.action) {
      case "guide":
        return guide();
      case "privacy":
        return modal(
          "사진 보관 안내",
          "<p>로그인 정보는 Firebase 인증에, 사진·얼굴 특징·결과는 현재 브라우저의 계정별 저장소에 보관합니다. 사진은 외부로 업로드하지 않습니다. 사용 후 로그아웃하고 원본과 ZIP을 따로 보관하세요. 기기 소유자는 브라우저 저장소를 열 수 있으므로 개인 기기를 사용하세요.</p>",
        );
      case "pick":
        return $("file-picker").click();
      case "folder":
        return $("folder-picker").click();
      case "start":
        return project.run();
      case "pause":
        project.pause();
        return notify("현재 파일을 마친 뒤 일시정지합니다.");
      case "add-child":
        return childDialog();
      case "rematch":
        await project.rematch();
        return render();
      case "select-visible":
        reviewItems()
          .slice(page * 48, (page + 1) * 48)
          .forEach((m) => selected.add(m.id));
        return render();
      case "clear-selection":
        selected.clear();
        return render();
      case "batch-assign":
        return assignmentDialog([...selected]);
      case "batch-exclude":
        if (!selected.size) throw new Error("사진을 선택하세요.");
        await project.assign([...selected], [], true);
        return render();
      case "reanalyze":
        if (!selected.size) throw new Error("사진을 선택하세요.");
        return project.reanalyze([...selected]);
      case "trash":
        if (!selected.size) throw new Error("사진을 선택하세요.");
        await project.trash([...selected]);
        return render();
      case "prev-page":
        page = Math.max(0, page - 1);
        return render();
      case "next-page":
        page++;
        return render();
      case "import-portable":
        return $("portable-picker").click();
      case "backup":
        await project.backup("사용자 상태 백업");
        return render();
      case "csv":
        return download(
          new Blob(
            [
              csv([
                ["아이 이름", "반", "사진", "영상", "합계"],
                ...statistics(data.kids, data.media).map((r) => [
                  r.name,
                  r.group_name,
                  r.photos,
                  r.videos,
                  r.total,
                ]),
              ]),
            ],
            { type: "text/csv;charset=utf-8" },
          ),
          "PhotoJoy-통계.csv",
        );
    }
  });
});
document.addEventListener("change", (e) => {
  if (e.target.dataset.select) {
    e.target.checked
      ? selected.add(e.target.dataset.select)
      : selected.delete(e.target.dataset.select);
    $("selected-count").textContent = selected.size + "개 선택";
  }
});
document.addEventListener("submit", (event) => {
  const form = event.target,
    b = event.submitter;
  if (
    !["child-form", "assignment-form", "settings-form", "export-form"].includes(
      form.id,
    )
  )
    return;
  event.preventDefault();
  b.disabled = true;
  run(async () => {
    try {
      if (form.id === "child-form") {
        const id = await project.addChild(
          $("child-name").value,
          $("child-group").value,
          form.dataset.child || undefined,
        );
        if (form.dataset.fromFace)
          await project.correctFace(
            form.dataset.fromMedia,
            form.dataset.fromFace,
            id,
            true,
          );
        closeModal();
        await refresh();
        navigate("children");
        if (!form.dataset.fromFace && !form.dataset.child) {
          referenceChild = id;
          $("reference-picker").click();
        }
      }
      if (form.id === "assignment-form") {
        await project.assign(
          form.dataset.ids.split(","),
          [...form.querySelectorAll("[name=assignment]:checked")].map(
            (el) => el.value,
          ),
        );
        closeModal();
        await refresh();
        await render();
      }
      if (form.id === "settings-form") {
        await project.saveSettings({
          sensitivity: $("sensitivity").value,
          unit: $("unit").value,
          minFacePixels: Number($("min-pixels").value),
          minRelative: Number($("min-relative").value),
        });
        await project.rematch();
        await refresh();
        await render();
        notify("설정과 정리 결과를 갱신했습니다.");
      }
      if (form.id === "export-form") {
        notify("ZIP을 준비하고 있습니다…");
        const r = await makeExports(project, {
          children: [
            ...form.querySelectorAll("[name=export-child]:checked"),
          ].map((el) => el.value),
          start: $("export-start").value,
          end: $("export-end").value,
          all: b.value === "all",
        });
        await render();
        notify(
          r.length
            ? `${r.length}개 ZIP을 준비했습니다. 발송은 직접 진행해 주세요.`
            : "선택 기간에 정리된 사진이 없습니다.",
        );
      }
    } catch (error) {
      if ($("modal-error")) $("modal-error").textContent = error.message;
      throw error;
    } finally {
      b.disabled = false;
    }
  });
});
for (const id of ["file-picker", "folder-picker"])
  $(id).addEventListener("change", (e) =>
    run(async () => {
      const files = [...e.target.files].filter((f) =>
        /\.(jpe?g|png|webp|heic|heif|gif|bmp|mp4|mov|m4v|webm|mkv|mts)$/i.test(
          f.name,
        ),
      );
      e.target.value = "";
      enqueuing = true;
      try {
        notify(`${files.length}개 원본을 작업 큐에 보관합니다…`);
        await project.enqueue(files);
      } finally {
        enqueuing = false;
        await refresh();
      }
      notify("파일 추가가 끝났습니다. 자동 분류 시작을 누르세요.");
    }),
  );
$("reference-picker").addEventListener("change", (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  run(() => registerReferences(files));
});
$("close-modal").onclick = closeModal;
document.addEventListener("keydown", (e) => {
  if (e.key === "F1") {
    e.preventDefault();
    guide();
  }
});
function mode(next) {
  authMode = next;
  for (const id of ["login", "register"]) {
    $(id + "-tab").classList.toggle("active", id === next);
    $(id + "-tab").setAttribute("aria-selected", String(id === next));
  }
  $("password").autocomplete =
    next === "register" ? "new-password" : "current-password";
  $("password").minLength = next === "register" ? 10 : 1;
  $("password-help").hidden = next !== "register";
  $("auth-submit").textContent =
    next === "register" ? "계정 만들고 시작하기 →" : "로그인 →";
  $("auth-error").hidden = true;
}
$("login-tab").onclick = () => mode("login");
$("register-tab").onclick = () => mode("register");
$("show-password").onclick = () => {
  const show = $("password").type === "password";
  $("password").type = show ? "text" : "password";
  $("show-password").textContent = show ? "숨기기" : "보기";
  $("show-password").setAttribute("aria-pressed", String(show));
};
$("auth-form").onsubmit = async (e) => {
  e.preventDefault();
  $("auth-submit").disabled = true;
  try {
    await enter(
      await login(
        $("username").value,
        $("password").value,
        platform(),
        authMode === "register",
      ),
    );
  } catch (error) {
    authError(error.message);
  } finally {
    $("auth-submit").disabled = false;
  }
};
$("logout").onclick = () =>
  run(async () => {
    if (project?.running || enqueuing)
      throw new Error("일시정지 후 현재 파일 처리가 끝나면 로그아웃하세요.");
    await logout();
    showLogin();
  });
window.addEventListener("beforeunload", (e) => {
  if (project?.running || enqueuing) {
    e.preventDefault();
    e.returnValue = "";
  }
});
async function boot() {
  try {
    await authReady;
    $("google-button").innerHTML =
      '<button id="google-login" class="google-placeholder wide"><b class="google-g">G</b> Google로 로그인</button>';
    $("google-state").textContent = "Google 계정으로 간편하게 시작하세요.";
    $("google-login").onclick = async () => {
      $("google-login").disabled = true;
      $("google-state").textContent =
        "열린 Google 창에서 로그인을 완료해 주세요.";
      try {
        await enter(await signInGoogle(platform()));
      } catch (error) {
        authError(error.message);
      } finally {
        $("google-login").disabled = false;
        $("google-state").textContent = "Google 계정으로 간편하게 시작하세요.";
      }
    };
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "text-button";
    reset.textContent = "비밀번호를 잊으셨나요?";
    reset.onclick = async () => {
      try {
        await resetPassword($("username").value);
        authError("등록된 이메일이라면 재설정 안내가 전송됩니다.");
      } catch (error) {
        authError(error.message);
      }
    };
    $("auth-form").append(reset);
    const guess = /Android/i.test(navigator.userAgent)
      ? "android"
      : /iPhone|iPad/i.test(navigator.userAgent)
        ? "iphone"
        : "windows";
    document.querySelector(`[name=platform][value=${guess}]`).checked = true;
    try {
      await enter(getSession());
    } catch {
      showLogin();
    }
    onAccountChanged((account) => {
      if (!account && user) showLogin();
    });
  } catch (error) {
    authError(error.message);
  }
}
boot();

$("portable-picker").addEventListener("change", (e) => {
  const files = [...e.target.files];
  e.target.value = "";
  run(async () => {
    notify("기존 자료를 브라우저 안으로 가져오고 있습니다…");
    const count = await importPortable(project, files);
    await refresh();
    await render();
    notify(
      `${count}개 백업 파일을 가져왔습니다. 기존 배정과 참고 얼굴을 보존했습니다.`,
    );
  });
});
