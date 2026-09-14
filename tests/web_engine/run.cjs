/* Build newsletters with the website's REAL engine, outside a browser.
 *
 * Loads the vendored Pyodide runtime from web/pyodide/, the packages the
 * page loads (read from web/app.js, so the list cannot drift from the
 * page), and the committed web/meridian-bundle.zip, then calls
 * scripts.webapp.build_from_bytes on each .docx given -- the call the page
 * makes. tests/test_web_engine.py compares the result with the desktop
 * build of the same files.
 *
 * Usage: node tests/web_engine/run.cjs <web dir> <output.json> <file.docx>...
 */
"use strict";

const fs = require("fs");
const path = require("path");

const [webDir, outPath, ...docxPaths] = process.argv.slice(2);
if (!webDir || !outPath || docxPaths.length === 0) {
  console.error("usage: node run.cjs <web dir> <output.json> <file.docx>...");
  process.exit(2);
}
const pyodideDir = path.join(webDir, "pyodide");

// A Node Buffer is often a view into a larger shared pool. Pyodide wants
// exactly the file's bytes, which is what fetch() hands the page.
const exact = (buf) => buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);

// Pyodide takes a wheel's name from the text after the last "/", so a
// Windows path with backslashes would make the whole path the "name".
const posix = (p) => p.split(path.sep).join("/");

function pagePackages() {
  const appJs = fs.readFileSync(path.join(webDir, "app.js"), "utf8");
  const match = appJs.match(/const PY_PACKAGES = \[([\s\S]*?)\];/);
  if (!match) throw new Error("PY_PACKAGES not found in web/app.js");
  const entries = [...match[1].replace(/\/\/[^\n]*/g, "").matchAll(/"([^"]+)"/g)];
  return entries.map(([, entry]) => (entry.startsWith("./pyodide/")
    ? posix(path.join(pyodideDir, entry.slice("./pyodide/".length)))
    : entry));
}

const BUILD = `
import json, sys
from importlib.metadata import version
if "/repo" not in sys.path:
    sys.path.insert(0, "/repo")
from scripts.webapp import build_from_bytes

r = build_from_bytes(bytes(docx_bytes.to_py()), issue=7)
json.dumps({
    "ok": r.ok,
    "subject": r.subject,
    "html": r.html,
    "plaintext": r.plaintext,
    "errors": list(r.errors),
    "section_count": r.section_count,
    "photo_count": r.photo_count,
    "python": sys.version.split()[0],
    "versions": {name: version(name) for name in (
        "css-inline", "beautifulsoup4", "jinja2", "lxml", "pillow", "python-docx")},
})
`;

async function main() {
  const { loadPyodide } = require(path.join(pyodideDir, "pyodide.js"));
  const pyodide = await loadPyodide({ indexURL: posix(pyodideDir) + "/" });
  await pyodide.loadPackage(pagePackages(), { messageCallback: () => {} });

  pyodide.FS.mkdir("/repo");
  pyodide.FS.chdir("/repo");
  pyodide.unpackArchive(exact(fs.readFileSync(path.join(webDir, "meridian-bundle.zip"))), "zip");

  const results = {};
  for (const docxPath of docxPaths) {
    pyodide.globals.set("docx_bytes", new Uint8Array(exact(fs.readFileSync(docxPath))));
    results[path.basename(docxPath)] = JSON.parse(pyodide.runPython(BUILD));
  }
  fs.writeFileSync(outPath, JSON.stringify(results));
}

main().catch((error) => {
  console.error(String((error && error.stack) || error));
  process.exit(1);
});
