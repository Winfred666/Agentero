#!/usr/bin/env node

import { execFileSync, spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import {
	access,
	mkdir,
	readFile,
	rename,
	rm,
	stat,
	writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(SCRIPT_DIR, "../..");
const TEST_APP_NAME = "Agentero Test";
const TEST_APP_IDENTIFIER = "com.poco-ai.agentero.test";
const PRODUCTION_APP_IDENTIFIER = "com.poco-ai.agentero";
const TEST_CONFIG = path.join(REPO_ROOT, "src-tauri/tauri.test.conf.json");
const TEST_VAULT = path.join(REPO_ROOT, "tmp/agentero-test-vault");
const INSTALL_ROOT = path.join(os.homedir(), "Applications");
const INSTALLED_APP = path.join(INSTALL_ROOT, `${TEST_APP_NAME}.app`);
const XDG_CONFIG_HOME = process.env.XDG_CONFIG_HOME?.trim()
	? path.resolve(process.env.XDG_CONFIG_HOME)
	: path.join(os.homedir(), ".config");
const TEST_OPEN_REQUEST = path.join(
	XDG_CONFIG_HOME,
	"agentero-test/cli-open-request.json",
);
const TEST_LOG = path.join(
	os.homedir(),
	"Library/Logs",
	TEST_APP_IDENTIFIER,
	"agentero.log",
);

function phase(label) {
	console.log(`\n==> ${label}`);
}

function run(command, args, options = {}) {
	const result = spawnSync(command, args, {
		cwd: REPO_ROOT,
		stdio: "inherit",
		...options,
	});
	if (result.error) throw result.error;
	if (result.status !== 0) {
		throw new Error(
			`${command} ${args.join(" ")} exited with ${result.status}`,
		);
	}
}

async function exists(target) {
	try {
		await access(target);
		return true;
	} catch {
		return false;
	}
}

function plistValue(appPath, key) {
	return execFileSync(
		"plutil",
		[
			"-extract",
			key,
			"raw",
			"-o",
			"-",
			path.join(appPath, "Contents/Info.plist"),
		],
		{ encoding: "utf8" },
	).trim();
}

async function assertTestBundle(appPath) {
	const identifier = plistValue(appPath, "CFBundleIdentifier");
	if (identifier !== TEST_APP_IDENTIFIER) {
		throw new Error(
			`refusing test install: ${appPath} has bundle id ${identifier}`,
		);
	}
	const scheme = plistValue(appPath, "CFBundleURLTypes.0.CFBundleURLSchemes.0");
	if (scheme !== "agentero-test") {
		throw new Error(`test bundle has unexpected URL scheme ${scheme}`);
	}
	const executable = plistValue(appPath, "CFBundleExecutable");
	for (const required of [
		path.join(appPath, "Contents/MacOS", executable),
		path.join(appPath, "Contents/MacOS/agentero-cli"),
		path.join(appPath, "Contents/Frameworks/libpdfium.dylib"),
	]) {
		if (!(await exists(required))) {
			throw new Error(`incomplete test bundle: missing ${required}`);
		}
	}
	return executable;
}

function runningTestPids(executable) {
	const expected = `${INSTALLED_APP}/Contents/MacOS/${executable}`;
	const lines = execFileSync("ps", ["-axo", "pid=,command="], {
		encoding: "utf8",
	}).split("\n");
	return lines
		.filter((line) => line.includes(expected))
		.map((line) => Number(line.trim().split(/\s+/, 1)[0]))
		.filter((pid) => Number.isInteger(pid) && pid > 0);
}

async function wait(ms) {
	await new Promise((resolve) => setTimeout(resolve, ms));
}

async function writeTestVaultOpenRequest() {
	await mkdir(path.dirname(TEST_OPEN_REQUEST), { recursive: true });
	const temporary = `${TEST_OPEN_REQUEST}.${process.pid}.tmp`;
	await writeFile(
		temporary,
		JSON.stringify(
			{ path: TEST_VAULT, ts: Math.floor(Date.now() / 1000) },
			null,
			2,
		),
	);
	await rename(temporary, TEST_OPEN_REQUEST);
}

async function stopInstalledTestApp(executable) {
	let pids = runningTestPids(executable);
	if (pids.length === 0) return;
	try {
		execFileSync(
			"osascript",
			["-e", `tell application id "${TEST_APP_IDENTIFIER}" to quit`],
			{ stdio: "ignore", timeout: 5000 },
		);
	} catch {
		// Fall back to SIGTERM below when Launch Services cannot address the app.
	}
	await wait(1500);
	pids = runningTestPids(executable);
	for (const pid of pids) {
		try {
			process.kill(pid, "SIGTERM");
		} catch (error) {
			if (error?.code !== "ESRCH") throw error;
		}
	}
	await wait(1000);
	if (runningTestPids(executable).length > 0) {
		throw new Error("Agentero Test did not quit before installation");
	}
}

async function installTestApp(builtApp, executable) {
	await mkdir(INSTALL_ROOT, { recursive: true });
	const staging = path.join(
		INSTALL_ROOT,
		`.agentero-test-installing-${process.pid}.app`,
	);
	const backup = path.join(
		INSTALL_ROOT,
		`.agentero-test-previous-${process.pid}.app`,
	);
	await rm(staging, { recursive: true, force: true });
	await rm(backup, { recursive: true, force: true });
	run("ditto", [builtApp, staging]);
	await assertTestBundle(staging);
	run("codesign", ["--force", "--deep", "--sign", "-", staging]);
	run("codesign", ["--verify", "--deep", "--strict", staging]);

	const hadPrevious = await exists(INSTALLED_APP);
	if (hadPrevious) {
		await assertTestBundle(INSTALLED_APP);
		await stopInstalledTestApp(executable);
		await rename(INSTALLED_APP, backup);
	}

	try {
		await rename(staging, INSTALLED_APP);
	} catch (error) {
		if (hadPrevious && (await exists(backup))) {
			await rename(backup, INSTALLED_APP);
		}
		throw error;
	}
	await rm(backup, { recursive: true, force: true });
	await assertTestBundle(INSTALLED_APP);
}

async function productionAppSnapshots() {
	const candidates = [
		"/Applications/Agentero.app",
		path.join(os.homedir(), "Applications/Agentero.app"),
	];
	const snapshots = [];
	for (const appPath of candidates) {
		const plist = path.join(appPath, "Contents/Info.plist");
		if (!(await exists(plist))) continue;
		const identifier = plistValue(appPath, "CFBundleIdentifier");
		if (identifier !== PRODUCTION_APP_IDENTIFIER) {
			throw new Error(`${appPath} has unexpected bundle id ${identifier}`);
		}
		const bytes = await readFile(plist);
		snapshots.push({
			appPath,
			hash: createHash("sha256").update(bytes).digest("hex"),
		});
	}
	return snapshots;
}

async function assertProductionAppsUnchanged(snapshots) {
	for (const snapshot of snapshots) {
		const bytes = await readFile(
			path.join(snapshot.appPath, "Contents/Info.plist"),
		);
		const hash = createHash("sha256").update(bytes).digest("hex");
		if (hash !== snapshot.hash) {
			throw new Error(`production app metadata changed: ${snapshot.appPath}`);
		}
	}
}

async function waitForLogLine(executable, offset, expectedLog, description) {
	for (let attempt = 0; attempt < 40; attempt += 1) {
		if (runningTestPids(executable).length === 0) {
			throw new Error("Agentero Test exited during launch verification");
		}
		if (await exists(TEST_LOG)) {
			const bytes = await readFile(TEST_LOG);
			const start = bytes.length >= offset ? offset : 0;
			if (bytes.subarray(start).toString("utf8").includes(expectedLog)) return;
		}
		await wait(500);
	}
	throw new Error(`${description} was not confirmed in ${TEST_LOG}`);
}

if (process.platform !== "darwin") {
	throw new Error("pnpm test:macos is only supported on macOS");
}

const config = JSON.parse(await readFile(TEST_CONFIG, "utf8"));
if (
	config.productName !== TEST_APP_NAME ||
	config.identifier !== TEST_APP_IDENTIFIER ||
	!config.build?.beforeBuildCommand?.includes(
		"VITE_AGENTERO_MACOS_TEST_BUILD=1",
	) ||
	config.plugins?.updater?.endpoints?.length !== 0
) {
	throw new Error("tauri.test.conf.json does not preserve test-app isolation");
}
const productionSnapshots = await productionAppSnapshots();

phase("Prepare clean-tree Tauri inputs");
run("pnpm", ["cli:ensure"]);
run("pnpm", ["pdfium:stage"]);

phase("Lint TypeScript and Rust");
run("pnpm", ["lint"]);

const vitest = path.join(REPO_ROOT, "node_modules/.bin/vitest");
const timingSensitiveTests = [
	"test/library-scope.test.ts",
	"test/pdf-citation-dest-keys.test.ts",
];
phase("Run timing-sensitive frontend tests in isolated processes");
for (const testFile of timingSensitiveTests) {
	run(vitest, ["run", testFile]);
}

phase("Run the remaining frontend tests");
run(vitest, [
	"run",
	...timingSensitiveTests.flatMap((testFile) => ["--exclude", testFile]),
]);

phase("Run Rust workspace tests");
run("cargo", ["test", "--workspace"], {
	env: { ...process.env, AGENTERO_SKIP_NETWORK: "1" },
});

phase("Rebuild and verify the disposable test Vault");
if (path.dirname(TEST_VAULT) !== path.join(REPO_ROOT, "tmp")) {
	throw new Error(`unsafe test Vault path: ${TEST_VAULT}`);
}
await rm(TEST_VAULT, { recursive: true, force: true });
run("node", ["test/scripts/create-demo-vault.mjs", TEST_VAULT]);
run("node", ["test/scripts/create-demo-vault.mjs", "--verify", TEST_VAULT]);

phase("Build the isolated macOS app bundle");
run("pnpm", [
	"exec",
	"tauri",
	"build",
	"--config",
	"src-tauri/tauri.test.conf.json",
	"--bundles",
	"app",
	"--ci",
]);
const metadata = JSON.parse(
	execFileSync("cargo", ["metadata", "--no-deps", "--format-version", "1"], {
		cwd: REPO_ROOT,
		encoding: "utf8",
	}),
);
const builtApp = path.join(
	metadata.target_directory,
	"release/bundle/macos",
	`${TEST_APP_NAME}.app`,
);
const executable = await assertTestBundle(builtApp);

phase(`Install ${INSTALLED_APP}`);
await installTestApp(builtApp, executable);

phase("Launch the test app and open the test Vault");
let logOffset = 0;
try {
	logOffset = (await stat(TEST_LOG)).size;
} catch {
	// The first local-test launch creates the identifier-scoped log directory.
}
run("open", ["-na", INSTALLED_APP]);
await waitForLogLine(
	executable,
	logOffset,
	"op start app_ready",
	"test app readiness",
);
await writeTestVaultOpenRequest();
await waitForLogLine(
	executable,
	logOffset,
	`op end vault_open_request ok=true path=${TEST_VAULT}`,
	"test Vault open",
);
await assertProductionAppsUnchanged(productionSnapshots);

console.log(`\nPASS\n  App:   ${INSTALLED_APP}`);
console.log(`  ID:    ${TEST_APP_IDENTIFIER}`);
console.log(`  Vault: ${TEST_VAULT}`);
if (productionSnapshots.length > 0) {
	console.log("  Production Agentero app metadata: unchanged");
}
