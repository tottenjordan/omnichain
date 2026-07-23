import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { useErrorReporter } from "../ErrorToast";
import { looksLikeMultipleChanges } from "../oneChange";
import type { GenerateResponse, Session, Shot } from "../types";

interface Props {
  session: Session;
  onUpdated: (session: Session) => void;
  onNext: () => void;
}

export function DailiesStage({ session, onUpdated, onNext }: Props) {
  const { report } = useErrorReporter();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  // Signed playback URLs keyed by shot id, captured from generate/edit responses.
  const [signedUrls, setSignedUrls] = useState<Record<string, string>>({});
  const [instruction, setInstruction] = useState("");

  const refresh = async (resp: GenerateResponse) => {
    if (resp.signed_url) {
      setSignedUrls((prev) => ({ ...prev, [resp.shot_id]: resp.signed_url as string }));
    }
    onUpdated(await api.getSession(session.id));
  };

  const generate = useMutation({
    mutationFn: (shotId: string) => api.generateShot(session.id, shotId),
    onSuccess: refresh,
    onError: report,
  });

  const edit = useMutation({
    mutationFn: (vars: { shotId: string; instruction: string }) =>
      api.editShot(session.id, vars.shotId, vars.instruction),
    onSuccess: async (resp) => {
      setInstruction("");
      await refresh(resp);
    },
    onError: report,
  });

  const approve = useMutation({
    mutationFn: (shotId: string) => api.approveShot(session.id, shotId),
    onSuccess: refresh,
    onError: report,
  });

  const shots = session.shots.slice().sort((a, b) => a.index - b.index);
  const selected = shots.find((s) => s.id === selectedId) ?? null;
  const multiChange = looksLikeMultipleChanges(instruction);
  const allApproved = shots.length > 0 && shots.every((s) => s.status === "approved");

  const submitEdit = () => {
    if (!selected || multiChange || !instruction.trim()) return;
    edit.mutate({ shotId: selected.id, instruction });
  };

  return (
    <section className="card">
      <h2>3 · Dailies</h2>
      <div className="dailies">
        <div className="clip-grid">
          {shots.map((shot) => (
            <ClipTile
              key={shot.id}
              shot={shot}
              signedUrl={signedUrls[shot.id]}
              selected={shot.id === selectedId}
              generating={generate.isPending && generate.variables === shot.id}
              onSelect={() => setSelectedId(shot.id)}
              onGenerate={() => generate.mutate(shot.id)}
              onApprove={() => approve.mutate(shot.id)}
            />
          ))}
        </div>

        <aside className="chat-panel">
          {!selected && <p className="muted">Select a shot to edit it conversationally.</p>}
          {selected && (
            <>
              <h3>
                Shot {selected.index + 1} · <span className="muted">{selected.status}</span>
              </h3>

              <div className="versions">
                {selected.versions.length === 0 && <p className="muted">No versions yet.</p>}
                {selected.versions.map((v) => (
                  <div key={v.version} className="version">
                    <strong>v{v.version}</strong>
                    <span>{v.instruction ?? "initial generation"}</span>
                  </div>
                ))}
              </div>

              {selected.versions.length > 0 && (
                <div className="editor">
                  <p className="hint">One change per turn — the model keeps everything else.</p>
                  <textarea
                    rows={2}
                    placeholder="e.g. Change the jacket to green"
                    value={instruction}
                    onChange={(e) => setInstruction(e.target.value)}
                  />
                  {multiChange && (
                    <p className="warn">
                      That looks like more than one change. Split it into separate edits.
                    </p>
                  )}
                  <div className="row">
                    <button
                      onClick={submitEdit}
                      disabled={edit.isPending || multiChange || !instruction.trim()}
                    >
                      {edit.isPending ? "Editing…" : "Send edit"}
                    </button>
                    <button
                      className="approve"
                      onClick={() => approve.mutate(selected.id)}
                      disabled={approve.isPending || selected.status === "approved"}
                    >
                      {selected.status === "approved" ? "Approved ✓" : "Approve"}
                    </button>
                  </div>
                </div>
              )}
            </>
          )}
        </aside>
      </div>

      <button className="primary" onClick={onNext} disabled={!allApproved}>
        {allApproved ? "Go to Final Cut →" : "Approve every shot to continue"}
      </button>
    </section>
  );
}

interface TileProps {
  shot: Shot;
  signedUrl: string | undefined;
  selected: boolean;
  generating: boolean;
  onSelect: () => void;
  onGenerate: () => void;
  onApprove: () => void;
}

function ClipTile({ shot, signedUrl, selected, generating, onSelect, onGenerate, onApprove }: TileProps) {
  const hasClip = shot.versions.length > 0;
  return (
    <div className={`clip-tile ${selected ? "selected" : ""}`} onClick={onSelect}>
      <div className="clip-head">
        <span className="badge">Shot {shot.index + 1}</span>
        <span className={`status status-${shot.status}`}>{shot.status}</span>
      </div>
      {signedUrl ? (
        <video src={signedUrl} controls preload="metadata" />
      ) : (
        <div className="clip-placeholder">{hasClip ? "clip ready (re-open to play)" : "not generated"}</div>
      )}
      <p className="clip-draft">{shot.draft_text}</p>
      <div className="row">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onGenerate();
          }}
          disabled={generating}
        >
          {generating ? "Generating…" : hasClip ? "Regenerate" : "Generate"}
        </button>
        {hasClip && shot.status !== "approved" && (
          <button
            className="approve"
            onClick={(e) => {
              e.stopPropagation();
              onApprove();
            }}
          >
            Approve
          </button>
        )}
      </div>
    </div>
  );
}
