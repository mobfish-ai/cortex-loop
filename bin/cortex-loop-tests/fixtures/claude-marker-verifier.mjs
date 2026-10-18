import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const marker = resolve(process.cwd(), "claude-native-smoke-marker.txt");
const expected = "claude-cli-native-smoke-v1\n";
const actual = readFileSync(marker, "utf8");
if (actual !== expected) {
  console.error(`MARKER_VERIFY_FAIL expected=${JSON.stringify(expected)} actual=${JSON.stringify(actual)}`);
  process.exit(1);
}
console.log(`MARKER_VERIFIED path=${marker} bytes=${Buffer.byteLength(actual)}`);
