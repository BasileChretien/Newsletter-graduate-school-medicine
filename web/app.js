/* MERIDIAN newsletter builder -- browser front end.
 *
 * This file deliberately contains NO newsletter logic. It boots
 * Pyodide, unpacks `meridian-bundle.zip` (the real `scripts/` package
 * plus templates, locales and brand images) into the virtual
 * filesystem, and calls `scripts.webapp.build_from_bytes`. Every
 * decision about parsing, rendering, inlining, validating and drafting
 * is made by the same Python the desktop launcher runs -- there is no
 * second implementation here to drift out of sync.
 *
 * Pyodide is pinned to 0.29.x on purpose: `css_inline` (the Rust-backed
 * CSS inliner the whole email layout depends on) ships in that line's
 * distribution. The 314.x line moved to ABI 2026_0 and has no
 * `css_inline` build yet, so bumping the version in index.html without
 * checking will break the page at install time.
 */

// The one address that is legitimate. Shown in the footer and used by
// the frame-buster, so an editor always has something to compare the
// address bar against.
const CANONICAL_URL =
  "https://basilechretien.github.io/Newsletter-graduate-school-medicine/";
const SOURCE_URL =
  "https://github.com/BasileChretien/Newsletter-graduate-school-medicine";

/* Everything below is served from this origin — see
 * `web/vendor_pyodide.py`. Nothing is fetched from a CDN or from PyPI at
 * runtime, which is what lets the CSP narrow to `'self'`.
 *
 * These load via `pyodide.loadPackage`, not micropip: with a local
 * `indexURL` the runtime resolves them straight out of the vendored
 * lockfile, so micropip and its network access are not needed at all.
 * `python-docx` is the exception — absent from Pyodide's lockfile, so it
 * is vendored as a wheel and loaded by path. */
const PYODIDE_INDEX_URL = "./pyodide/";

const PY_PACKAGES = [
  "css_inline",             // the load-bearing one (Rust)
  "jinja2",
  "beautifulsoup4",
  "pillow",                 // resizes photos before they are sent
  // python-docx's own dependency. It has to be named here because
  // python-docx is loaded BY PATH below, so the lockfile resolver never
  // sees its requirements and pulls nothing in for it. Omitting it gets
  // you a page that loads every package successfully and then dies on
  // `from lxml import etree`.
  "lxml",
  "./pyodide/python_docx-1.2.0-py3-none-any.whl",
];

/* The page can be framed by anyone: GitHub Pages sends no
 * X-Frame-Options, and `frame-ancestors` is specified as ignored inside
 * a <meta> tag, so no CSP on this host can stop it. That matters more
 * than a typical clickjacking risk, because a clone reproduces every
 * trust claim on this page verbatim -- it IS the same static file -- and
 * the page's whole job is to persuade an editor to hand over an
 * unpublished document and ~50 institutional addresses. Framing the real
 * tool inside a hostile wrapper is the cheapest version of that attack:
 * everything works, so nothing feels wrong. */
if (window.top !== window.self) {
  document.documentElement.textContent =
    "This page must be opened directly, not inside another site. " +
    "The only genuine address is " + CANONICAL_URL;
  try { window.top.location = window.self.location; } catch { /* opaque */ }
  throw new Error("refusing to run inside a frame");
}

const REPO_MOUNT = "/repo";
const OUTPUT_DIR = "/output";

// ---------------------------------------------------------------- i18n

/* Bilingual JA/EN parity is a project requirement for anything an
 * editor reads. Keys match the `data-i18n` attributes in index.html. */
const STRINGS = {
  en: {
    tagline: "Newsletter of the Graduate School of Medicine – Nagoya University",
    privacy: "Your Word file is processed entirely inside this browser tab. Nothing is uploaded — there is no server to upload it to.",
    bootStarting: "Starting the newsletter engine…",
    bootPackages: "Loading the newsletter engine (first time only, about 10 seconds)…",
    bootBundle: "Loading the MERIDIAN toolkit…",
    bootReady: "Ready.",
    bootFailed: "The newsletter engine could not start. Check your internet connection and reload the page.",
    step1: "Choose your Word file",
    step2: "Settings",
    dropHere: "Drop <code>issue-N.docx</code> here, or click to choose",
    fileHint: "Only .docx files. The file stays on this device.",
    issueLabel: "Issue number",
    issueHint: "Used to name the files and to group this issue's photos.",
    bccLabel: "BCC recipients",
    optional: "(optional)",
    bccHint: "Pre-fills the BCC field of the draft. These addresses stay on this device and are written only into the draft file you download.",
    buildBtn: "Build the newsletter",
    working: "Building…",
    resultsTitle: "Result",
    dlEml: "Download the email draft (.eml)",
    dlHtml: "Download the HTML",
    emlHint: "Double-click the .eml file: Outlook opens it as a ready-to-send draft, with the subject, the BCC list and the photos already in place. Add the To: address and press Send.",
    previewTitle: "Preview",
    previewHint: "This is what recipients will see.",
    footer: "Your document never leaves this device. Nothing is sent anywhere.",
    provenance: "This tool will never ask you for a password. If a page that looks like this one does, close it. The only genuine address is:",
    sourceLink: "View the source code",
    verdictOk: "Ready to send.",
    verdictBad: "Not ready — please fix the points below in Word and build again.",
    tooBig: "That file is too large for the browser version (over 40 MB). In Word, use File → Compress Pictures, save, and try again — or use the desktop launcher, which has no size limit.",
    oneFileOnly: "Please drop one .docx file at a time.",
    technicalDetail: "Technical detail (for the maintainer)",
    bootBundleMissing: "The toolkit files are missing from this page. This is a setup problem on the server, not something you can fix — please tell whoever published the page.",
    bccPlaceholder: "one address per line",
    sumBytes: "bytes",
    sumSubject: "Subject",
    sumSections: "Sections",
    sumPhotos: "Photos embedded",
    sumNotEmbedded: "not embedded",
    sumRecipients: "BCC recipients",
    sumSize: "Size",
    crashed: "Something went wrong while building. This is a bug in the toolkit, not in your Word file.",
    notDocx: "That is not a .docx file. Save your newsletter from Word as .docx and try again.",
  },
  ja: {
    tagline: "名古屋大学大学院医学系研究科 ニュースレター",
    privacy: "Wordファイルはこのブラウザのタブ内だけで処理されます。アップロードは行われません（送信先のサーバーがそもそも存在しません）。",
    bootStarting: "ニュースレター作成エンジンを起動しています…",
    bootPackages: "作成エンジンを読み込んでいます（初回のみ、約10秒）…",
    bootBundle: "MERIDIANツールキットを読み込んでいます…",
    bootReady: "準備ができました。",
    bootFailed: "作成エンジンを起動できませんでした。インターネット接続を確認して、ページを再読み込みしてください。",
    step1: "Wordファイルを選ぶ",
    step2: "設定",
    dropHere: "<code>issue-N.docx</code> をここにドラッグするか、クリックして選んでください",
    fileHint: ".docxファイルのみ。ファイルはこの端末から出ません。",
    issueLabel: "号数",
    issueHint: "ファイル名と、この号の写真のまとめ方に使われます。",
    bccLabel: "BCC宛先",
    optional: "（任意）",
    bccHint: "下書きのBCC欄にあらかじめ入力されます。これらのアドレスはこの端末から出ず、ダウンロードする下書きファイルにのみ書き込まれます。",
    buildBtn: "ニュースレターを作成",
    working: "作成中…",
    resultsTitle: "結果",
    dlEml: "メール下書き（.eml）をダウンロード",
    dlHtml: "HTMLをダウンロード",
    emlHint: ".emlファイルをダブルクリックしてください。Outlookが、件名・BCC・写真がすでに入った送信可能な下書きとして開きます。宛先（To）を入力して送信してください。",
    previewTitle: "プレビュー",
    previewHint: "受信者にはこのように表示されます。",
    footer: "文書がこの端末から出ることはありません。データはどこにも送信されません。",
    provenance: "このツールがパスワードを尋ねることは決してありません。よく似た画面でパスワードを求められた場合は、閉じてください。正規のアドレスは次のとおりです：",
    sourceLink: "ソースコードを見る",
    verdictOk: "送信できます。",
    verdictBad: "まだ送信できません。以下の点をWordで修正して、もう一度作成してください。",
    tooBig: "このファイルはブラウザ版には大きすぎます（40MB超）。Word の「ファイル → 図の圧縮」で小さくして保存し直すか、サイズ制限のないデスクトップ版ランチャーをご利用ください。",
    oneFileOnly: "一度にドラッグできる .docx ファイルは 1 つだけです。",
    technicalDetail: "技術的な詳細（管理者向け）",
    bootBundleMissing: "このページにツールキットのファイルが見つかりません。サーバー側の設定の問題ですので、ページの公開担当者にお伝えください。",
    bccPlaceholder: "1 行に 1 件ずつ",
    sumBytes: "バイト",
    sumSubject: "件名",
    sumSections: "セクション数",
    sumPhotos: "埋め込んだ写真",
    sumNotEmbedded: "件は未埋め込み",
    sumRecipients: "BCC宛先数",
    sumSize: "サイズ",
    crashed: "作成中に問題が発生しました。これはWordファイルではなく、ツールキット側の不具合です。",
    notDocx: ".docxファイルではありません。Wordから.docx形式で保存し直してください。",
  },
};

let lang = (navigator.language || "en").toLowerCase().startsWith("ja") ? "ja" : "en";
const t = (key) => (STRINGS[lang] && STRINGS[lang][key]) || STRINGS.en[key] || key;

function applyLanguage() {
  document.documentElement.lang = lang;
  for (const el of document.querySelectorAll("[data-i18n]")) {
    const value = t(el.dataset.i18n);
    // Setting `textContent` on an element that CONTAINS another
    // `[data-i18n]` element destroys that child. The BCC label wraps a
    // `<span data-i18n="optional">`, so this loop deleted the
    // "(optional)" hint on every single page load -- in both languages,
    // since the span was detached before its own turn came round. Skip
    // container elements; their descendants are handled on their own.
    if (el.querySelector("[data-i18n]")) continue;
    // A few strings carry inline markup (<code>). They are authored
    // here, never derived from the DOCX, so this is not a sink for
    // untrusted content.
    if (value.includes("<")) el.innerHTML = value;
    else el.textContent = value;
  }
  // Attribute translations -- `placeholder` and `title` are read by
  // editors and screen readers respectively, and were English-only.
  for (const el of document.querySelectorAll("[data-i18n-attr]")) {
    const [attr, key] = el.dataset.i18nAttr.split(":");
    el.setAttribute(attr, t(key));
  }
  const canon = document.getElementById("canonical-url");
  if (canon) canon.textContent = CANONICAL_URL;
  const srcLink = document.getElementById("source-link");
  if (srcLink) srcLink.href = SOURCE_URL;
  for (const btn of document.querySelectorAll(".lang-switch button")) {
    const active = btn.dataset.lang === lang;
    btn.classList.toggle("is-active", active);
    // The visual state is a colour swap, which a screen reader cannot see.
    btn.setAttribute("aria-pressed", String(active));
  }
  // The boot line is driven imperatively through its phases, so it
  // cannot be bound to a static `data-i18n` -- doing so meant a language
  // toggle during (or after) boot rewound the message to "Starting…",
  // erasing a failure notice and its "reload the page" instruction.
  if (bootKey) {
    bootText.textContent = t(bootKey) + (bootDetail ? `\n\n${bootDetail}` : "");
  }
  // Re-localising is not a navigation event: keep the viewport and the
  // focus ring exactly where the editor left them.
  if (fatalKey) showFatal(t(fatalKey), fatalDetail, { focus: false });
  else if (lastResult) renderResult(lastResult, { focus: false });
}

// ---------------------------------------------------------------- boot

const $ = (id) => document.getElementById(id);
const bootBox = $("boot");
const bootText = $("boot-text");
let pyodide = null;
let buildFn = null;
let lastResult = null;
let chosenFile = null;
// Boot state is tracked by KEY, not by rendered text, so a language
// toggle re-renders the current phase instead of rewinding it.
let bootKey = "bootStarting";
let bootDetail = "";
let fatalKey = null;
let fatalDetail = "";

function setBoot(key, detail = "") {
  bootKey = key;
  bootDetail = detail;
  bootText.textContent = t(key) + (detail ? `\n\n${detail}` : "");
}

async function boot() {
  try {
    setBoot("bootStarting");
    pyodide = await loadPyodide({ indexURL: PYODIDE_INDEX_URL });

    setBoot("bootPackages");
    // One call with the whole list so the runtime resolves shared
    // dependencies once (jinja2/MarkupSafe, beautifulsoup4/soupsieve,
    // python-docx/lxml).
    await pyodide.loadPackage(PY_PACKAGES);

    setBoot("bootBundle");
    const res = await fetch("meridian-bundle.zip");
    if (!res.ok) {
      // A 404 here means the bundle was left out of the deploy, or the
      // page is served from the wrong subdirectory. Telling the editor
      // to check their internet connection would send them chasing
      // something they cannot fix -- this one is the maintainer's.
      throw new Error(`bundle HTTP ${res.status}`);
    }
    const zip = await res.arrayBuffer();
    pyodide.FS.mkdir(REPO_MOUNT);
    pyodide.FS.chdir(REPO_MOUNT);
    await pyodide.unpackArchive(zip, "zip");
    pyodide.FS.mkdir(OUTPUT_DIR);

    buildFn = pyodide.runPython(GLUE);

    bootBox.hidden = true;
    $("builder").hidden = false;
  } catch (err) {
    bootBox.classList.add("verdict", "bad");
    // Stop the spinner: leaving it turning next to a failure message
    // reads as "still working", so the editor waits instead of reloading.
    for (const s of bootBox.querySelectorAll(".spinner")) s.remove();
    setBoot(String(err).includes("bundle HTTP") ? "bootBundleMissing"
                                                : "bootFailed", String(err));
    console.error(err);
  }
}

/* Python glue. Kept as a single string rather than a file in the
 * bundle so that the bundle stays exactly "the toolkit", with no
 * web-only module smuggled inside it. */
const GLUE = `
import json, shutil, sys
from pathlib import Path
sys.path.insert(0, "${REPO_MOUNT}")
from scripts.webapp import build_from_bytes

_WORKDIR = Path("/build")

def _web_build(js_bytes, issue, image_mode, bcc):
    # A fixed, wiped-per-run workdir. The default is a fresh temp
    # directory, which is right for a process that exits -- but this
    # "process" is a browser tab that may build a dozen times, and
    # Pyodide's filesystem is memory. Each build copies in the brand
    # images and extracts every photo, so temp dirs would accumulate
    # for the lifetime of the tab.
    shutil.rmtree(_WORKDIR, ignore_errors=True)
    result = build_from_bytes(
        bytes(js_bytes.to_py()),
        issue=int(issue),
        image_mode=image_mode,
        # Passed raw: splitting and validating recipients is
        # \`scripts.recipients.sanitize_addresses\`' job, so the browser
        # and the CLI apply exactly the same rules.
        bcc=bcc or None,
        workdir=_WORKDIR,
    )
    out = Path("${OUTPUT_DIR}")
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    # Written to the virtual FS rather than returned, so a 1 MB .eml
    # and a preview full of base64 photos never cross the JS bridge
    # as strings.
    if result.eml is not None:
        p = out / f"issue-{int(issue)}.eml"
        p.write_bytes(result.eml)
        paths["eml"] = str(p)
    if result.html:
        p = out / f"issue-{int(issue)}.html"
        p.write_text(result.html, encoding="utf-8")
        paths["html"] = str(p)
    if result.preview_html:
        p = out / "preview.html"
        p.write_text(result.preview_html, encoding="utf-8")
        paths["preview"] = str(p)
    return json.dumps({
        "ok": result.ok,
        "issue": int(issue),
        "subject": result.subject,
        "errors": list(result.errors),
        "warnings": list(result.warnings),
        "section_count": result.section_count,
        "photo_count": result.photo_count,
        "unembedded_photo_count": result.unembedded_photo_count,
        "recipient_count": result.recipient_count,
        "size_bytes": result.size_bytes,
        "image_mode": result.image_mode,
        "paths": paths,
    })

_web_build
`;

// ------------------------------------------------------------ file pick

const dropzone = $("dropzone");
const fileInput = $("file");

/* Peak memory is several times the file size: the ArrayBuffer, a copy
 * in the Pyodide heap, the extracted photos, and base64 data URIs for
 * the preview. Past this the WASM heap dies and the editor gets either
 * "Aw, Snap" or a RangeError under a misleading banner. 40 MB is far
 * above any real newsletter. */
const MAX_DOCX_BYTES = 40 * 1024 * 1024;

function clearChosenFile() {
  chosenFile = null;
  $("file-chosen").hidden = true;
  $("build").disabled = true;
  // Reset the input too, so re-picking the SAME file still fires `change`.
  fileInput.value = "";
}

function rejectFile(key) {
  // Disarm before complaining. Leaving the previous file loaded meant an
  // editor who picked issue-7.docx, then dropped issue-8.doc and saw it
  // rejected, could press Build and get a flawless, wrong newsletter.
  clearChosenFile();
  showFileError(t(key));
}

function chooseFile(file) {
  if (!file) {
    // Dropping a folder, or an attachment dragged straight out of
    // Outlook, yields an empty file list. Silence here looks like the
    // page ignoring them.
    rejectFile("notDocx");
    return;
  }
  if (!file.name.toLowerCase().endsWith(".docx")) {
    rejectFile("notDocx");
    return;
  }
  if (file.size > MAX_DOCX_BYTES) {
    rejectFile("tooBig");
    return;
  }
  clearFileError();
  chosenFile = file;
  const chosen = $("file-chosen");
  chosen.textContent = `${file.name} (${(file.size / 1024).toFixed(0)} KB)`;
  chosen.hidden = false;
  $("build").disabled = false;

  // Pre-fill the issue number from `issue-7.docx`, since that is the
  // naming convention the launcher already enforces.
  const m = file.name.match(/^issue-(\d+)\.docx$/i);
  if (m) $("issue").value = m[1];
}

function showFileError(message) {
  // Rendered next to the drop zone, not in the "Result" panel below the
  // fold: no result was produced, and an editor who drops a PDF on a
  // laptop would otherwise see the page do nothing at all.
  const box = $("file-error");
  box.textContent = message;
  box.hidden = false;
}

function clearFileError() {
  $("file-error").hidden = true;
}

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
fileInput.addEventListener("change", () => {
  chooseFile(fileInput.files[0]);
  // The real <input> is hidden and cannot hold focus, so after the file
  // dialog closes a keyboard user would be left with focus on <body>.
  dropzone.focus();
});

for (const evt of ["dragenter", "dragover"]) {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.add("is-over");
  });
}
for (const evt of ["dragleave", "drop"]) {
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.classList.remove("is-over");
  });
}
dropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length > 1) { rejectFile("oneFileOnly"); return; }
  chooseFile(e.dataTransfer.files[0]);
});

/* Releasing the file a few pixels outside the drop zone -- over the
 * masthead, the settings card, the page margin -- otherwise hits the
 * browser's default handler, which NAVIGATES the tab to the .docx. The
 * page is gone, the loaded Pyodide runtime with it, and the tool looks
 * like it crashed. Catch it at the window and treat a near-miss as a
 * successful drop. */
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.target.closest("#dropzone")) return;   // already handled above
  if (!buildFn) return;                        // still booting
  const files = e.dataTransfer?.files;
  if (files && files.length) {
    if (files.length > 1) rejectFile("oneFileOnly");
    else chooseFile(files[0]);
  }
});

// --------------------------------------------------------------- build

$("builder").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!chosenFile || !buildFn) return;
  await runBuild();
});

async function runBuild() {
  $("build").disabled = true;
  $("working").hidden = false;
  // The build blocks the main thread for seconds; without this a screen
  // reader announces nothing at all while it runs.
  $("builder").setAttribute("aria-busy", "true");

  try {
    const bytes = new Uint8Array(await chosenFile.arrayBuffer());

    // Yield a frame so the spinner paints before Pyodide blocks the
    // main thread for a few seconds.
    await new Promise((r) => setTimeout(r, 0));

    /* Always "cid". The hosted-URL mode is deliberately not offered
     * here: inside Pyodide there is no env var and no `git`, so
     * `get_default_repo()` always falls back to the UPSTREAM
     * coordinates -- a forking institution would email photos pointing
     * at someone else's repository, at paths that only exist in their
     * own. The page also cannot publish, so the URLs would 404 even
     * upstream. `build_from_bytes` still supports both modes for a
     * server or notebook caller that can actually push. */
    const json = buildFn(bytes, $("issue").value, "cid", $("bcc").value);
    lastResult = JSON.parse(json);
    fatalKey = null;
    renderResult(lastResult);
  } catch (err) {
    console.error(err);
    fatalKey = "crashed";
    fatalDetail = String(err);
    showFatal(t("crashed"), fatalDetail);
  } finally {
    $("build").disabled = false;
    $("working").hidden = true;
    $("builder").removeAttribute("aria-busy");
  }
}

// -------------------------------------------------------------- results

let objectUrls = [];

function revokeObjectUrls() {
  objectUrls.forEach((u) => URL.revokeObjectURL(u));
  objectUrls = [];
}

function blobUrl(path, type) {
  const data = pyodide.FS.readFile(path);
  const url = URL.createObjectURL(new Blob([data], { type }));
  objectUrls.push(url);
  return url;
}

/* `focus: false` is used by the language toggle. Both render paths end
 * by scrolling to the results heading and moving focus there, which is
 * right when a build finishes -- and wrong when `applyLanguage()`
 * re-runs them purely to re-localise existing text. Without the opt-out,
 * a keyboard or screen-reader user who clicked EN/JA was yanked down the
 * page for a reason they never asked for. */
function showFatal(message, detail = "", { focus = true } = {}) {
  lastResult = null;
  revokeObjectUrls();
  $("results").hidden = false;
  $("verdict").className = "verdict bad";
  $("verdict").textContent = message;
  $("summary").innerHTML = "";
  $("messages").innerHTML = "";
  // Raw technical detail goes in a collapsed <details>, so the editor
  // reads one human sentence and a maintainer can still expand the
  // traceback. Previously both were concatenated into one run-on line.
  const box = $("messages");
  if (detail) {
    const d = document.createElement("details");
    const s = document.createElement("summary");
    s.textContent = t("technicalDetail");
    const pre = document.createElement("pre");
    pre.textContent = detail;
    d.append(s, pre);
    box.append(d);
  }
  $("downloads").hidden = true;
  clearPreview();
  if (focus) focusResults();
}

function clearPreview() {
  // `removeAttribute("src")` does NOT unload an already-loaded document,
  // so a failed build sat under a red "Not ready" banner showing a
  // preview of the previous, good newsletter.
  $("preview").removeAttribute("src");
  $("preview").srcdoc = "";
  $("preview-block").hidden = true;
}

function focusResults() {
  const h = $("results-heading");
  h.scrollIntoView({
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
      ? "auto" : "smooth",
    block: "start",
  });
  h.focus();
}

function renderResult(res, { focus = true } = {}) {
  // Revoke here rather than at the start of a build: this function also
  // re-runs when the editor switches language, and each pass mints new
  // blob URLs for the same files. Revoking at build time leaked one set
  // per language toggle.
  revokeObjectUrls();
  $("results").hidden = false;

  const verdict = $("verdict");
  verdict.className = `verdict ${res.ok ? "ok" : "bad"}`;
  verdict.textContent = res.ok ? t("verdictOk") : t("verdictBad");

  const rows = [
    [t("sumSubject"), res.subject],
    [t("sumSections"), String(res.section_count)],
    [t("sumPhotos"), res.unembedded_photo_count
      ? `${res.photo_count} (${res.unembedded_photo_count} ${t("sumNotEmbedded")})`
      : String(res.photo_count)],
    [t("sumRecipients"), String(res.recipient_count)],
    [t("sumSize"), `${res.size_bytes.toLocaleString(lang)} ${t("sumBytes")}`],
  ];
  $("summary").innerHTML = "";
  for (const [term, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = term;
    const dd = document.createElement("dd");
    dd.textContent = value;                      // never innerHTML: DOCX content
    $("summary").append(dt, dd);
  }

  const messages = $("messages");
  messages.innerHTML = "";
  for (const text of res.errors) messages.append(message("error", text));
  for (const text of res.warnings) messages.append(message("warn", text));

  const downloads = $("downloads");
  if (res.ok && res.paths.eml) {
    downloads.hidden = false;
    // Filenames captured from the RESULT, not from the live #issue
    // field: editing that box after a build (or toggling language,
    // which re-renders) would otherwise rename the file without
    // rebuilding its contents.
    const eml = $("dl-eml");
    eml.href = blobUrl(res.paths.eml, "message/rfc822");
    eml.download = `issue-${res.issue}.eml`;
    const html = $("dl-html");
    html.href = blobUrl(res.paths.html, "text/html");
    html.download = `issue-${res.issue}.html`;
  } else {
    downloads.hidden = true;
  }

  if (res.paths.preview) {
    // `srcdoc` rather than a blob URL: it renders under `sandbox=""`
    // without depending on how a given browser version scopes blob URLs
    // to the creating origin, and it leaves one less object URL alive.
    // The photos are `data:` URIs, so nothing else needs fetching.
    $("preview").removeAttribute("src");
    $("preview").srcdoc = pyodide.FS.readFile(res.paths.preview,
                                              { encoding: "utf8" });
    $("preview-block").hidden = false;
  } else {
    clearPreview();
  }
  if (focus) focusResults();
}

function message(kind, text) {
  const div = document.createElement("div");
  div.className = `msg ${kind}`;
  div.textContent = text;   // validator text can quote the DOCX
  return div;
}

// ----------------------------------------------------------------- init

for (const btn of document.querySelectorAll(".lang-switch button")) {
  btn.addEventListener("click", () => { lang = btn.dataset.lang; applyLanguage(); });
}

applyLanguage();
boot();
