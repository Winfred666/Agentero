import { describe, expect, it } from "vitest";
import {
	backgroundTaskPolicyForBuild,
	backgroundTasksStore,
	mapDownloadProgress,
	startBackgroundTask,
	updateBackgroundTask,
} from "@/lib/core/background-tasks";

describe("background task download progress", () => {
	it("pins and retains diagnostics only for the macOS test build", () => {
		expect(backgroundTaskPolicyForBuild(true)).toEqual({
			keepPanelOpen: true,
			autoPruneFinished: false,
		});
		expect(backgroundTaskPolicyForBuild(false)).toEqual({
			keepPanelOpen: false,
			autoPruneFinished: true,
		});
	});

	it("maps sequential PDF and TeX phases into one overall progress", () => {
		expect(mapDownloadProgress("pdf", 0)).toBe(0);
		expect(mapDownloadProgress("pdf", 80)).toBe(40);
		expect(mapDownloadProgress("tex", 0)).toBe(50);
		expect(mapDownloadProgress("tex", 60)).toBe(80);
		expect(mapDownloadProgress("tex", 100)).toBe(100);
		expect(mapDownloadProgress("parse", null)).toBe(90);
	});

	it("never regresses a task when a late phase event arrives", () => {
		const id = startBackgroundTask({
			kind: "download",
			title: "test",
			progress: 40,
		});

		updateBackgroundTask(id, { progress: 20 });

		expect(
			backgroundTasksStore.getState().tasks.find((task) => task.id === id)
				?.progress,
		).toBe(40);

		backgroundTasksStore.setState({ tasks: [], expanded: false });
	});
});
