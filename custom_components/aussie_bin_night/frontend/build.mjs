import { cp, mkdir } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const here = new URL(".", import.meta.url);
await mkdir(new URL("../static/", here), { recursive: true });
await cp(
  fileURLToPath(new URL("src/bin-night-card.js", here)),
  fileURLToPath(new URL("../static/bin-night-card.js", here)),
);
