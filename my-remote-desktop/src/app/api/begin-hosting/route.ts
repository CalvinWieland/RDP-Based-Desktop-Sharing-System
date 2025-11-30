import { spawn } from "child_process";
import path from "path";
import fs from "fs";

// host post request route handler
export async function POST(req: Request) {
  const { sessionCode, videoQuality } = await req.json();

  // get the path to the host.py
  const scriptPath = await path.join(process.cwd(), "../rdp_app/host.py");

  // get python exectuable path based on windows/mac
  const pythonPath =
    process.platform === "win32"
      ? path.join(process.cwd(), "../.venv/Scripts/python.exe")
      : path.join(process.cwd(), "../.venv/bin/python3");

  // run python script to host
  const py = spawn(pythonPath, [scriptPath], {
    env: {
      ...process.env,
      SESSION_CODE: sessionCode,
      VIDEO_QUALITY: videoQuality,
    },
  });

  // set up logging for data and errors
  py.stdout.on("data", (data) => console.log("[PY]", data.toString()));
  py.stderr.on("data", (data) => console.error("[PY ERR]", data.toString()));

  py.on("close", (code) => console.log(`Python process exited with code ${code}`));

  return new Response(JSON.stringify({ status: "started" }), {
    headers: { "Content-Type": "application/json" },
  });
}
