const fs = require("node:fs");
const path = require("node:path");
const output = path.resolve(__dirname,"../frontend/vendor");
fs.mkdirSync(output,{recursive:true});
for (const [source,name] of [
  ["three/build/three.module.min.js","three.module.min.js"],
  ["three/build/three.core.min.js","three.core.min.js"],
  ["three/LICENSE","THREE-LICENSE.txt"],
  ["gsap/dist/gsap.min.js","gsap.min.js"],
  ["gsap/dist/ScrollTrigger.min.js","ScrollTrigger.min.js"],
]) {
  fs.copyFileSync(path.resolve(__dirname,"../node_modules",source),path.join(output,name));
}
const gsap = require("../node_modules/gsap/package.json");
fs.writeFileSync(path.join(output,"GSAP-LICENSE.txt"),`GSAP ${gsap.version}\nCopyright 2025, GreenSock. All rights reserved.\n${gsap.license}\nDistribution license headers are preserved in both vendored files.\n`);
console.log("Vendored pinned landing dependencies and licenses.");
