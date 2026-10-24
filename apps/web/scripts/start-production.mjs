import { cpSync, existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";

// Next's standalone bundle requires public and static assets beside server.js.
const root = process.cwd();
const buildDir = process.env.GROUNDTRUTH_BUILD_DIR || ".next";
const standalone = path.join(root, buildDir, "standalone");
if (!existsSync(path.join(standalone, "server.js"))) {
  throw new Error(
    "No standalone production build exists. Run npm run build first.",
  );
}
for (const [from, to] of [
  ["public", "public"],
  [`${buildDir}/static`, `${buildDir}/static`],
]) {
  const source = path.join(root, from);
  if (existsSync(source))
    cpSync(source, path.join(standalone, to), { recursive: true });
}
const args = process.argv.slice(2);
const option = (name, fallback) => {
  const index = args.indexOf(name);
  return index >= 0 ? args[index + 1] : fallback;
};
const port = option("--port", process.env.PORT || "3505");
const hostname = option("--hostname", process.env.HOSTNAME || "127.0.0.1");
const child = spawn(process.execPath, [path.join(standalone, "server.js")], {
  cwd: standalone,
  stdio: "inherit",
  env: {
    ...process.env,
    NODE_ENV: "production",
    PORT: port,
    HOSTNAME: hostname,
  },
});
for (const signal of ["SIGINT", "SIGTERM"])
  process.on(signal, () => child.kill(signal));
child.on("error", (error) => {
  process.stderr.write(`${error.message}\n`);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code || 0;
});
