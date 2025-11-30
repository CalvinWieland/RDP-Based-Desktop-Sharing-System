"use client"

import { useState } from "react"
import "./remote-desktop.css"

type VideoQuality = "low" | "medium" | "high" | "ultra"

export default function RemoteDesktopPage() {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [videoQuality, setVideoQuality] = useState<VideoQuality>("medium")
  const [sessionId, setSessionId] = useState("")
  const [connectionMode, setConnectionMode] = useState<"host" | "join">("host")
  
  const handleStartHosting = async () => {
    console.log("Starting host session:", { username, videoQuality });
    await fetch("/api/begin-hosting", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionCode: `${username}-${Date.now()}`,
        videoQuality,
      }),
    });
    alert("Host session started!");
  };

    const handleJoinSession = async () => {
    console.log("Starting host session:", { username, videoQuality });
    await fetch("/api/join", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        sessionCode: `${username}-${Date.now()}`,
        videoQuality,
      }),
    });
    alert("Host session started!");
  };

  const qualityOptions = [
    { value: "low", label: "Low (720p)" },
    { value: "medium", label: "Medium (1080p)" },
    { value: "high", label: "High (1440p)" },
    { value: "ultra", label: "Ultra (4K)" },
  ]

  return (
    <div className="rdp-container">
      <div className="rdp-card">
        <div className="rdp-card-header">
          <h1 className="rdp-card-title">Remote Desktop</h1>
          <p className="rdp-card-description">Connect to or host a remote desktop session</p>
        </div>
        <div className="rdp-card-content">
          <div className="rdp-tabs-list">
            <button
              className={`rdp-tab-trigger ${connectionMode === "host" ? "active" : ""}`}
              onClick={() => setConnectionMode("host")}
            >
              Host Session
            </button>
            <button
              className={`rdp-tab-trigger ${connectionMode === "join" ? "active" : ""}`}
              onClick={() => setConnectionMode("join")}
            >
              Join Session
            </button>
          </div>
          <div className={`rdp-tab-content ${connectionMode === "host" ? "active" : ""}`}>
            <div className="rdp-space-y-4">
              {/* 
              <div className="rdp-form-group">
                <label htmlFor="host-username" className="rdp-label">
                  Username
                </label>
                <input
                  id="host-username"
                  type="text"
                  placeholder="Enter username"
                  className="rdp-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>

              <div className="rdp-form-group">
                <label htmlFor="host-password" className="rdp-label">
                  Password
                </label>
                <input
                  id="host-password"
                  type="password"
                  placeholder="Enter password"
                  className="rdp-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <div className="rdp-form-group">
                <label htmlFor="host-quality" className="rdp-label">
                  Video Quality
                </label>
                <select
                  id="host-quality"
                  className="rdp-select-trigger"
                  value={videoQuality}
                  onChange={(e) => setVideoQuality(e.target.value as VideoQuality)}
                >
                  {qualityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
               */}

              <button className="rdp-button" onClick={handleStartHosting} disabled={!username || !password}>
                Start Hosting
              </button>
            </div>
          </div>

          <div className={`rdp-tab-content ${connectionMode === "join" ? "active" : ""}`}>
            <div className="rdp-space-y-4">
              {/*
              <div className="rdp-form-group">
                <label htmlFor="join-username" className="rdp-label">
                  Username
                </label>
                <input
                  id="join-username"
                  type="text"
                  placeholder="Enter username"
                  className="rdp-input"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </div>

              <div className="rdp-form-group">
                <label htmlFor="join-password" className="rdp-label">
                  Password
                </label>
                <input
                  id="join-password"
                  type="password"
                  placeholder="Enter password"
                  className="rdp-input"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              <div className="rdp-form-group">
                <label htmlFor="session-id" className="rdp-label">
                  Session ID
                </label>
                <input
                  id="session-id"
                  type="text"
                  placeholder="Enter session ID to join"
                  className="rdp-input"
                  value={sessionId}
                  onChange={(e) => setSessionId(e.target.value)}
                />
              </div>

              <div className="rdp-form-group">
                <label htmlFor="join-quality" className="rdp-label">
                  Video Quality
                </label>
                <select
                  id="join-quality"
                  className="rdp-select-trigger"
                  value={videoQuality}
                  onChange={(e) => setVideoQuality(e.target.value as VideoQuality)}
                >
                  {qualityOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              */}

              <button
                className="rdp-button"
                onClick={handleJoinSession}
                disabled={!username || !password || !sessionId}
              >
                Join Session
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
