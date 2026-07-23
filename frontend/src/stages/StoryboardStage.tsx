import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { useErrorReporter } from "../ErrorToast";
import type { Session } from "../types";

interface Props {
  session: Session;
  onUpdated: (session: Session) => void;
  onNext: () => void;
}

export function StoryboardStage({ session, onUpdated, onNext }: Props) {
  const { report } = useErrorReporter();
  const [targetSeconds, setTargetSeconds] = useState(45);

  const storyboard = useMutation({
    mutationFn: () => api.storyboard(session.id, targetSeconds),
    onSuccess: onUpdated,
    onError: report,
  });

  const hasShots = session.shots.length > 0;

  return (
    <section className="card">
      <h2>2 · Storyboard</h2>
      <p className="muted">
        The director agent slices “{session.concept}” into 3–6 sub-10s beats. Edit any shot's
        text before generating.
      </p>

      <div className="row">
        <label className="field inline">
          <span>Target length (s)</span>
          <input
            type="number"
            min={30}
            max={60}
            value={targetSeconds}
            onChange={(e) => setTargetSeconds(Number(e.target.value))}
          />
        </label>
        <button onClick={() => storyboard.mutate()} disabled={storyboard.isPending}>
          {storyboard.isPending ? "Slicing…" : hasShots ? "Re-slice" : "Generate storyboard"}
        </button>
      </div>

      {hasShots && (
        <div className="shot-cards">
          {session.shots
            .slice()
            .sort((a, b) => a.index - b.index)
            .map((shot) => (
              <div key={shot.id} className="shot-card">
                <div className="shot-head">
                  <span className="badge">Shot {shot.index + 1}</span>
                  <span className="muted">{shot.duration_s}s</span>
                </div>
                <textarea
                  rows={3}
                  value={shot.draft_text}
                  onChange={(e) => {
                    const shots = session.shots.map((s) =>
                      s.id === shot.id ? { ...s, draft_text: e.target.value } : s,
                    );
                    onUpdated({ ...session, shots });
                  }}
                />
              </div>
            ))}
        </div>
      )}

      {hasShots && (
        <button className="primary" onClick={onNext}>
          Go to Dailies →
        </button>
      )}
    </section>
  );
}
