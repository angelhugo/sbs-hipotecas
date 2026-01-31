import fs from "fs";
import path from "path";

const src = path.resolve("../data/hipotecarios_300_habiles.csv");
const dstDir = path.resolve("./public/data");
const dst = path.join(dstDir, "hipotecarios_300_habiles.csv");

fs.mkdirSync(dstDir, { recursive: true });
fs.copyFileSync(src, dst);

console.log("CSV copiado a public/data");
