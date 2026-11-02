/* Babel AST만 사용합니다. 사용자 프로젝트 코드를 require/import/eval 하지 않습니다. */
"use strict";
const fs = require("node:fs");
const path = require("node:path");
const parser = require("@babel/parser");
const HTTP = new Set(["get","post","put","patch","delete","options","head"]);
const NEXT = new Set(["GET","POST","PUT","PATCH","DELETE","OPTIONS","HEAD"]);
const SOURCE_EXT = /\.(js|jsx|ts|tsx|mjs|cjs|mts|cts)$/i;
const SKIP_KEYS = new Set(["loc", "start", "end", "extra", "comments", "tokens", "leadingComments", "trailingComments", "innerComments"]);

function nameOf(n) {
  if (!n || typeof n !== "object") return null;
  if (n.type === "Identifier") return n.name;
  if (n.type === "ThisExpression") return "this";
  if (n.type === "StringLiteral") return n.value;
  if (n.type === "MemberExpression" || n.type === "OptionalMemberExpression") {
    const object = nameOf(n.object);
    const prop = n.computed ? (n.property.type === "StringLiteral" ? n.property.value : null) : nameOf(n.property);
    return object && prop ? object + "." + prop : null;
  }
  if (n.type === "TSNonNullExpression" || n.type === "TSAsExpression") return nameOf(n.expression);
  return null;
}
function loc(n) { return (n.loc && n.loc.start && n.loc.start.line) || 1; }
function isFunction(n) { return n && ["ArrowFunctionExpression", "FunctionExpression"].includes(n.type); }
function nextRoutePath(p) {
  const parts = p.split("/");
  const k = parts.lastIndexOf("api");
  if (k === -1) return null;
  if (!/^route\.(js|ts|tsx|jsx)$/.test(parts[parts.length - 1])) return null;
  return "/" + parts.slice(k, -1).map(x => x.replace(/^\[(?:\.\.\.)?([^\]]+)\]$/, "{$1}")).join("/");
}
function parseOne(root, relative) {
  const abs = path.resolve(root, relative);
  if (!(abs === root || abs.startsWith(root + path.sep))) throw Error("invalid path");
  const real = fs.realpathSync(abs);
  if (!real.startsWith(root + path.sep) || !SOURCE_EXT.test(relative)) throw Error("unsafe source path");
  const stat = fs.statSync(real);
  if (!stat.isFile() || stat.size > 65536) throw Error("oversized source file");
  const source = fs.readFileSync(real, "utf8");
  const ts = /\.(ts|tsx|mts|cts)$/i.test(relative);
  const jsx = /\.(tsx|jsx)$/i.test(relative);
  const tree = parser.parse(source, {sourceType:"unambiguous", errorRecovery:false,
    plugins:[...(ts ? ["typescript"] : []), ...(jsx ? ["jsx"] : []), "decorators-legacy"]});
  const functions=[], imports=[], calls=[], routes=[];
  const seen = new Set();
  let visited=0;
  const routePath = nextRoutePath(relative);
  function recordFunction(name, node, kind) {
    if (!name || seen.has(name + ":" + loc(node))) return;
    seen.add(name + ":" + loc(node));
    functions.push({name, line:loc(node), kind:kind || "function"});
  }
  function walk(n, current, cls) {
    if (!n || typeof n !== "object") return;
    if (++visited > 120000) throw Error("AST node limit exceeded");
    if (Array.isArray(n)) { for (const item of n) walk(item, current, cls); return; }
    if (n.type === "ImportDeclaration") {
      const spec=n.source.value;
      if (typeof spec === "string" && spec.length <= 256) {
        const bindings = [];
        for (const s of n.specifiers || []) {
          const imported = s.type === "ImportDefaultSpecifier" ? "default" :
            s.type === "ImportNamespaceSpecifier" ? "*" : nameOf(s.imported);
          if (s.local && imported) bindings.push({local:s.local.name, imported});
        }
        imports.push({module:spec, bindings, line:loc(n)});
      }
      return;
    }
    if (n.type === "FunctionDeclaration") {
      const name=n.id && n.id.name;
      if (name) {
        recordFunction(name,n);
        if (routePath && NEXT.has(name)) routes.push({method:name, path:routePath, line:loc(n), handler:name});
      }
      walk(n.body,name||current,cls); return;
    }
    if (n.type === "ClassDeclaration") {
      const cname=n.id && n.id.name;
      walk(n.body,current,cname || cls); return;
    }
    if (n.type === "ClassMethod" || n.type === "ClassPrivateMethod") {
      const key=nameOf(n.key);
      const f=cls && key ? cls+"."+key : key;
      if(f) recordFunction(f,n,"method");
      walk(n.body,f||current,cls);return;
    }
    if (n.type === "VariableDeclarator" && n.id && n.id.type === "Identifier" && isFunction(n.init)) {
      const name=n.id.name;
      recordFunction(name,n,"function");
      if (routePath && NEXT.has(name)) routes.push({method:name,path:routePath,line:loc(n),handler:name});
      walk(n.init.body,name,cls);
      return;
    }
    if (n.type === "CallExpression" || n.type === "OptionalCallExpression") {
      const callee=nameOf(n.callee);
      if(current && callee && callee.length <= 160)
        calls.push({caller:current,callee,line:loc(n)});
      const pieces=callee && callee.split(".");
      const method=pieces && pieces[pieces.length-1].toLowerCase();
      if (callee && pieces.length===2 && HTTP.has(method) && ["app","router","server"].includes(pieces[0])) {
        const arg=n.arguments && n.arguments[0];
        const route=arg && arg.type==="StringLiteral" && arg.value.length<=160 ? arg.value : null;
        const handler=n.arguments && n.arguments[1] && nameOf(n.arguments[1]);
        if (route) routes.push({method:method.toUpperCase(),path:route,line:loc(n),handler:handler||null});
      }
    }
    for (const key of Object.keys(n)) {
      if (SKIP_KEYS.has(key)) continue;
      const value=n[key];
      if (value && typeof value === "object") walk(value,current,cls);
    }
  }
  walk(tree.program,null,null);
  return {path:relative,language:ts?"typescript":"javascript",functions,imports,calls,routes};
}
async function main() {
  let input="";
  for await (const chunk of process.stdin) {
    input+=chunk;
    if(input.length>256000) throw Error("too many file paths");
  }
  const args=JSON.parse(input);
  const root=fs.realpathSync(args.root);
  const results=[], errors=[];
  for (const p of args.files.slice(0,300)) {
    try { results.push(parseOne(root,p)); }
    catch(err) { errors.push({path:p,kind:"parse_failed",message:String(err.message).slice(0,140)}); }
  }
  process.stdout.write(JSON.stringify({files:results,errors})+"\n");
}
main().catch(err=>{process.stderr.write("JS AST error: "+err.message+"\n");process.exitCode=1;});
