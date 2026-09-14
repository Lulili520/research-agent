#!/usr/bin/env node
'use strict';
// Optional dependencies are local or resolved through NODE_PATH; no auto-install.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
const { createHash, randomUUID } = require('node:crypto');
const digest = data => createHash('sha256').update(data).digest('hex');
const escape = value => value.replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
async function main() {
  const args = process.argv.slice(2);
  if (args.includes('--help')) {
    console.log('Usage: export-pdf.cjs INPUT.md OUTPUT.pdf --font FONT.ttf [--heading-font FONT.ttf] [--browser EXECUTABLE]');
    return;
  }
  if (args.length < 4) throw new Error('Expected INPUT.md OUTPUT.pdf --font FONT.ttf (see --help)');
  const source = path.resolve(args[0]), output = path.resolve(args[1]);
  const opts = {};
  for (let i=2; i<args.length; i+=2) {
    if (!['--font','--heading-font','--browser'].includes(args[i]) || !args[i+1]) throw new Error('Unknown or incomplete option: '+args[i]);
    opts[args[i]] = path.resolve(args[i+1]);
  }
  if (!opts['--font']) throw new Error('--font is required');
  if (source === output || !/\.md$/i.test(source) || !/\.pdf$/i.test(output)) throw new Error('Use distinct .md input and .pdf output');
  for (const p of [source,...Object.values(opts)]) fs.accessSync(p,fs.constants.R_OK);
  const { chromium } = require('playwright');
  const MarkdownIt = require('markdown-it');
  const katex = require('katex');
  const texmath = require('markdown-it-texmath');
  const original = fs.readFileSync(source), src = original.toString('utf8');
  const errors = [], formulas = [];
  const engine = { renderToString(tex,options) {
    formulas.push(tex);
    try { return katex.renderToString(tex,{...options,throwOnError:true,strict:'error',trust:false}); }
    catch (e) { errors.push(e.message); throw e; }
  }};
  // Raw HTML is disabled: source is content, never executable script.
  const md = new MarkdownIt({html:true,typographer:false}).use(texmath,{engine,delimiters:'dollars'});
  // Filter only HTML tokens, preserving literal comments inside code blocks.
  for (const kind of ['html_inline','html_block']) md.renderer.rules[kind] = (tokens,i) => {
    const raw=tokens[i].content;
    return /^\s*<!--[\s\S]*?-->\s*$/.test(raw) ? '' : escape(raw);
  };
  const content = md.render(src);
  if (errors.length) throw new Error('Math parse error: '+errors.join('\n'));
  const title = src.match(/^#\s+(.+)$/m)?.[1] || path.basename(source,'.md');
  const css = fs.readFileSync(path.join(__dirname,'print.css'),'utf8');
  const provenance = {
    style_sha256: digest(css),
    exporter_sha256: digest(fs.readFileSync(__filename)),
    font_files: [...new Set([opts['--font'], opts['--heading-font'] || opts['--font']])].map(file => ({file, sha256:digest(fs.readFileSync(file))}))
  };
  const work = fs.mkdtempSync(path.join(os.tmpdir(),'research-pdf-'));
  fs.mkdirSync(path.dirname(output),{recursive:true});
  const pending = path.join(path.dirname(output),'.'+path.basename(output)+'.'+randomUUID()+'.tmp');
  let browser;
  try {
    const file = path.join(work,'report.html');
    fs.writeFileSync(file,`<!doctype html><html lang="zh"><head><meta charset="utf-8"><title>${escape(title)}</title><base href="${pathToFileURL(path.dirname(source)+path.sep).href}"><link rel="stylesheet" href="${pathToFileURL(require.resolve('katex/dist/katex.min.css')).href}"><style>@font-face{font-family:ReportBody;src:url('${pathToFileURL(opts['--font']).href}');font-weight:100 900;font-display:block}@font-face{font-family:ReportHeading;src:url('${pathToFileURL(opts['--heading-font'] || opts['--font']).href}');font-weight:100 900;font-display:block}\n${css}</style></head><body>${content}</body></html>`);
    browser = await chromium.launch({headless:true,...(opts['--browser']?{executablePath:opts['--browser']}:{}),args:['--no-sandbox','--allow-file-access-from-files']});
    const page = await browser.newPage();
    const failed=[];
    page.on('requestfailed',r=>failed.push(r.url()));
    await page.goto(pathToFileURL(file).href,{waitUntil:'networkidle'});
    await page.emulateMedia({media:'print'});
    // An image paragraph followed by an emphasized caption is a single figure.
    await page.evaluate(()=>{
      for (const p of [...document.querySelectorAll('p')]) {
        if (p.children.length!==1 || p.firstElementChild.tagName!=='IMG' || p.textContent.trim()) continue;
        const next=p.nextElementSibling;
        if (!next || next.tagName!=='P' || next.children.length!==1 || next.firstElementChild.tagName!=='EM') continue;
        const figure=document.createElement('figure'), caption=document.createElement('figcaption');
        p.before(figure); figure.append(p.firstElementChild);
        while(next.firstElementChild.firstChild) caption.append(next.firstElementChild.firstChild);
        figure.append(caption); p.remove(); next.remove();
      }
    });
    await page.evaluate(async()=>{
      await document.fonts.load('400 14px ReportBody');
      await document.fonts.load('600 18px ReportHeading');
      await document.fonts.ready;
      if (!document.fonts.check('400 14px ReportBody') || !document.fonts.check('600 18px ReportHeading')) throw new Error('Body font did not load');
      if ([...document.images].some(i=>!i.complete || i.naturalWidth===0)) throw new Error('An image did not load');
    });
    const audit = await page.evaluate(()=>({
      formulas:[...document.querySelectorAll('annotation[encoding="application/x-tex"]')].map(n=>n.textContent),
      errors:[...document.querySelectorAll('.katex-error')].map(n=>n.textContent),
      fonts:[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family)
    }));
    if (audit.errors.length || failed.length || JSON.stringify(audit.formulas)!==JSON.stringify(formulas)) throw new Error('Rendering mismatch: '+JSON.stringify({audit,failed}));
    await page.pdf({path:pending,format:'A4',preferCSSPageSize:true,printBackground:true,tagged:true,outline:true,displayHeaderFooter:true,headerTemplate:'<div></div>',footerTemplate:'<div style="width:100%;text-align:center;font-size:8px;color:#7a8995"><span class="pageNumber"></span></div>'});
    if (digest(fs.readFileSync(source)) !== digest(original)) throw new Error('Source changed during export; rerun');
    if (fs.readFileSync(pending).subarray(0,5).toString() !== '%PDF-') throw new Error('Invalid PDF output');
    fs.renameSync(pending,output);
    console.log(JSON.stringify({output,source_sha256:digest(original),pdf_sha256:digest(fs.readFileSync(output)),...provenance,formulas:formulas.length,fonts:audit.fonts,bytes:fs.statSync(output).size}));
  } finally {
    if (browser) await browser.close();
    fs.rmSync(work,{recursive:true,force:true});
    fs.rmSync(pending,{force:true});
  }
}
main().catch(e=>{console.error(e.message);process.exitCode=1;});
