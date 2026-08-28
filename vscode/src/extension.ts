import * as vscode from "vscode";

const tokenKey = "a2s.apiToken";
let activeRequest: AbortController | undefined;
let activeMissionId: string | undefined;

function settings(): { url: string; workspace: string } {
  const config = vscode.workspace.getConfiguration("a2s");
  return {
    url: config.get<string>("url", "http://127.0.0.1:8700").replace(/\/$/, ""),
    workspace: config.get<string>("workspace", "") ||
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath || ""
  };
}

async function apiRequest(context: vscode.ExtensionContext, path: string,
  method: string, body: unknown, signal?: AbortSignal): Promise<any> {
  const config = settings();
  const token = await context.secrets.get(tokenKey);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }
  const response = await fetch(`${config.url}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    signal
  });
  const result = await response.json() as { error?: string };
  if (!response.ok) {
    throw new Error(result.error || `A2S API returned HTTP ${response.status}`);
  }
  return result;
}

async function requestMission(context: vscode.ExtensionContext, goal: string,
  signal: AbortSignal): Promise<{ mission_id: string }> {
  const result = await apiRequest(context, "/api/mission", "POST",
    { goal, workspace: settings().workspace }, signal);
  if (!result.mission_id) {
    throw new Error("A2S API response has no mission_id");
  }
  return result as { mission_id: string };
}

async function requestStatus(context: vscode.ExtensionContext, missionId: string,
  signal: AbortSignal): Promise<any> {
  return apiRequest(context, `/api/mission/${encodeURIComponent(missionId)}`,
    "GET", undefined, signal);
}

async function requestCancel(context: vscode.ExtensionContext, missionId: string): Promise<void> {
  await apiRequest(context, `/api/mission/${encodeURIComponent(missionId)}/cancel`,
    "POST", { reason: "vscode" });
}

async function requestLearningReport(context: vscode.ExtensionContext): Promise<any> {
  return apiRequest(context, "/api/learning-report", "GET", undefined);
}

export function activate(context: vscode.ExtensionContext): void {
  const output = vscode.window.createOutputChannel("A2S");
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.command = "a2s.runMission";
  status.text = "$(rocket) A2S";
  status.tooltip = "Run an A2S mission";
  status.show();
  context.subscriptions.push(output, status);

  context.subscriptions.push(vscode.commands.registerCommand("a2s.cancelMission", () => {
    if (!activeRequest) {
      output.appendLine("No active mission request.");
      status.text = "$(rocket) A2S";
      return;
    }
    activeRequest.abort();
    if (activeMissionId) {
      void requestCancel(context, activeMissionId).then(() => {
        output.appendLine(`Remote cancellation requested: ${activeMissionId}`);
      }).catch((error: unknown) => {
        output.appendLine(`Remote cancellation failed: ${error instanceof Error ? error.message : String(error)}`);
      });
    } else {
      output.appendLine("Mission request cancelled locally.");
    }
    status.text = "$(circle-slash) A2S cancelled";
  }));

  context.subscriptions.push(vscode.commands.registerCommand("a2s.configureToken", async () => {
    const value = await vscode.window.showInputBox({ prompt: "A2S API token", password: true });
    if (value) {
      await context.secrets.store(tokenKey, value);
      vscode.window.showInformationMessage("A2S API token stored in VS Code SecretStorage.");
    }
  }));

  context.subscriptions.push(vscode.commands.registerCommand("a2s.showLearningReport", async () => {
    try {
      const report = await requestLearningReport(context);
      output.appendLine("A2S learning report:");
      output.appendLine(JSON.stringify(report, null, 2));
      output.show(true);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      output.appendLine(`Learning report failed: ${message}`);
      vscode.window.showErrorMessage(`A2S: ${message}`);
    }
  }));

  context.subscriptions.push(vscode.commands.registerCommand("a2s.runMission", async () => {
    const goal = await vscode.window.showInputBox({ prompt: "A2S mission goal" });
    if (!goal?.trim()) {
      return;
    }
    if (activeRequest) {
      vscode.window.showWarningMessage("An A2S mission request is already running.");
      return;
    }
    const controller = new AbortController();
    activeRequest = controller;
    activeMissionId = undefined;
    status.text = "$(sync~spin) A2S running";
    output.appendLine(`Mission queued; submitting to ${settings().url}`);
    try {
      const accepted = await requestMission(context, goal.trim(), controller.signal);
      activeMissionId = accepted.mission_id;
      status.text = "$(sync~spin) A2S accepted";
      output.appendLine(`Mission accepted: ${activeMissionId}`);
      vscode.window.showInformationMessage(`A2S mission accepted: ${activeMissionId}`);
      let seenEvents = 0;
      while (!controller.signal.aborted && activeMissionId) {
        await new Promise(resolve => setTimeout(resolve, 250));
        const state = await requestStatus(context, activeMissionId, controller.signal);
        const events = state.events || [];
        for (const event of events.slice(seenEvents)) {
          output.appendLine(`Task ${event.task_id}: ${event.status}`);
        }
        seenEvents = events.length;
        if (["done", "error", "cancelled"].includes(state.status)) {
          output.appendLine(`Mission ${activeMissionId}: ${state.status}`);
          break;
        }
      }
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : String(error);
      if (controller.signal.aborted) {
        output.appendLine("Mission request cancelled locally.");
      } else {
        output.appendLine(`Mission failed: ${message}`);
        vscode.window.showErrorMessage(`A2S: ${message}`);
      }
    } finally {
      if (activeRequest === controller) {
        activeRequest = undefined;
        activeMissionId = undefined;
      }
      status.text = "$(rocket) A2S";
    }
  }));
}

export function deactivate(): void {}