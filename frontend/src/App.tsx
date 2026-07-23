import { useState } from "react";
import type { Session } from "./types";
import { VisionStage } from "./stages/VisionStage";
import { StoryboardStage } from "./stages/StoryboardStage";
import { DailiesStage } from "./stages/DailiesStage";
import { FinalCutStage } from "./stages/FinalCutStage";

const STAGES = ["Vision", "Storyboard", "Dailies", "Final Cut"] as const;
export type Stage = (typeof STAGES)[number];

export function App() {
  const [stage, setStage] = useState<Stage>("Vision");
  const [session, setSession] = useState<Session | null>(null);

  const go = (next: Stage) => setStage(next);
  const reachedIndex = STAGES.indexOf(stage);

  return (
    <div className="app">
      <header className="app-header">
        <h1>🎬 OmniChain 🪄</h1>
        <p className="tagline">One concept → a stitched parody short, shot by shot.</p>
      </header>

      <nav className="stepper" aria-label="Wizard progress">
        {STAGES.map((s, i) => {
          const reachable = session !== null || i === 0;
          return (
            <button
              key={s}
              className={`step ${i === reachedIndex ? "active" : ""} ${i < reachedIndex ? "done" : ""}`}
              disabled={!reachable}
              onClick={() => reachable && setStage(s)}
            >
              <span className="step-num">{i + 1}</span>
              {s}
            </button>
          );
        })}
      </nav>

      <main className="stage">
        {stage === "Vision" && (
          <VisionStage
            onCreated={(s) => {
              setSession(s);
              go("Storyboard");
            }}
          />
        )}
        {stage === "Storyboard" && session && (
          <StoryboardStage
            session={session}
            onUpdated={setSession}
            onNext={() => go("Dailies")}
          />
        )}
        {stage === "Dailies" && session && (
          <DailiesStage session={session} onUpdated={setSession} onNext={() => go("Final Cut")} />
        )}
        {stage === "Final Cut" && session && <FinalCutStage session={session} />}
      </main>
    </div>
  );
}
