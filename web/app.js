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

const PY_PACKAGES = [
  "css_inline",      // the load-bearing one
  "python-docx",
  "jinja2",
  "beautifulsoup4",
  "requests",        // imported by scripts.validator at module level
];

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
    modeLabel: "Photos",
    modeCid: "Embed inside the email (recommended)",
    modeUrl: "Load from GitHub when opened",
    modeHint: "Embedding means recipients see the photos even on networks that block outside images, and nothing needs publishing first.",
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
    footer: "Runs offline after first load. Nothing is sent anywhere.",
    verdictOk: "Ready to send.",
    verdictBad: "Not ready — please fix the points below in Word and build again.",
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
    modeLabel: "写真",
    modeCid: "メールの中に埋め込む（推奨）",
    modeUrl: "開いたときにGitHubから読み込む",
    modeHint: "埋め込むと、外部画像を遮断するネットワークでも受信者に写真が表示され、事前の公開作業も不要です。",
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
    footer: "初回読み込み後はオフラインでも動作します。データはどこにも送信されません。",
    verdictOk: "送信できます。",
    verdictBad: "まだ送信できません。以下の点をWordで修正して、もう一度作成してください。",
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
    // A few strings carry inline markup (<code>). They are authored
    // here, never derived from the DOCX, so this is not a sink for
    // untrusted content.
    if (value.includes("<")) el.innerHTML = value;
    else el.textContent = value;
  }
  for (const btn of document.querySelectorAll(".lang-switch button")) {
    btn.classList.toggle("is-active", btn.dataset.lang === lang);
  }
  if (lastResult) renderResult(lastResult);
}

// ---------------------------------------------------------------- boot

const $ = (id) => document.getElementById(id);
const bootBox = $("boot");
const bootText = $("boot-text");
let pyodide = null;
let buildFn = null;
let lastResult = null;
let chosenFile = null;

async function boot() {
  try {
    bootText.textContent = t("bootStarting");
    pyodide = await loadPyodide();

    bootText.textContent = t("bootPackages");
    await pyodide.loadPackage("micropip");
    const micropip = pyodide.pyimport("micropip");
    await Promise.all(PY_PACKAGES.map((p) => micropip.install(p)));

    bootText.textContent = t("bootBundle");
    const zip = await (await fetch("meridian-bundle.zip")).arrayBuffer();
    pyodide.FS.mkdir(REPO_MOUNT);
    pyodide.FS.chdir(REPO_MOUNT);
    await pyodide.unpackArchive(zip, "zip");
    pyodide.FS.mkdir(OUTPUT_DIR);

    buildFn = pyodide.runPython(GLUE);

    bootBox.hidden = true;
    $("builder").hidden = false;
  } catch (err) {
    bootBox.classList.add("verdict", "bad");
    bootText.textContent = `${t("bootFailed")}\n\n${err}`;
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

function chooseFile(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".docx")) {
    showFatal(t("notDocx"));
    return;
  }
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

dropzone.addEventListener("click", () => fileInput.click());
dropzone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); fileInput.click(); }
});
fileInput.addEventListener("change", () => chooseFile(fileInput.files[0]));

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
dropzone.addEventListener("drop", (e) => chooseFile(e.dataTransfer.files[0]));

// --------------------------------------------------------------- build

$("builder").addEventListener("submit", async (e) => {
  e.preventDefault();
  if (!chosenFile || !buildFn) return;
  await runBuild();
});

async function runBuild() {
  $("build").disabled = true;
  $("working").hidden = false;

  try {
    const bytes = new Uint8Array(await chosenFile.arrayBuffer());

    // Yield a frame so the spinner paints before Pyodide blocks the
    // main thread for a few seconds.
    await new Promise((r) => setTimeout(r, 0));

    const json = buildFn(bytes, $("issue").value, $("mode").value,
                         $("bcc").value);
    lastResult = JSON.parse(json);
    renderResult(lastResult);
  } catch (err) {
    console.error(err);
    showFatal(`${t("crashed")}\n\n${err}`);
  } finally {
    $("build").disabled = false;
    $("working").hidden = true;
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

function showFatal(message) {
  lastResult = null;
  revokeObjectUrls();
  $("results").hidden = false;
  $("verdict").className = "verdict bad";
  $("verdict").textContent = message;
  $("summary").innerHTML = "";
  $("messages").innerHTML = "";
  $("downloads").hidden = true;
  $("preview").removeAttribute("src");
}

function renderResult(res) {
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
    [t("sumSize"), `${res.size_bytes.toLocaleString()} bytes`],
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
    const eml = $("dl-eml");
    eml.href = blobUrl(res.paths.eml, "message/rfc822");
    eml.download = `issue-${$("issue").value}.eml`;
    const html = $("dl-html");
    html.href = blobUrl(res.paths.html, "text/html");
    html.download = `issue-${$("issue").value}.html`;
  } else {
    downloads.hidden = true;
  }

  if (res.paths.preview) {
    $("preview").src = blobUrl(res.paths.preview, "text/html");
  }
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
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
