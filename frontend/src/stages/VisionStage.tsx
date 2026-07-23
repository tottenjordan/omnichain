import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "../api";
import { useErrorReporter } from "../ErrorToast";
import type { Character, Session } from "../types";

interface Props {
  onCreated: (session: Session) => void;
}

export function VisionStage({ onCreated }: Props) {
  const { report } = useErrorReporter();
  const [concept, setConcept] = useState("");
  const [styleTone, setStyleTone] = useState("");
  const [bucket, setBucket] = useState("");
  const [browsedBucket, setBrowsedBucket] = useState("");
  const [folder, setFolder] = useState("");
  const [masterAudio, setMasterAudio] = useState("");
  const [selectedChars, setSelectedChars] = useState<string[]>([]);

  const folders = useQuery({
    queryKey: ["folders", browsedBucket],
    queryFn: () => api.listFolders(browsedBucket),
    enabled: browsedBucket.length > 0,
  });

  const characters = useQuery({
    queryKey: ["characters", "global"],
    queryFn: () => api.listCharacters("global"),
  });

  const create = useMutation({
    mutationFn: () =>
      api.createSession({
        concept,
        style_tone: styleTone,
        gcs_bucket: bucket,
        gcs_folder: folder,
        master_audio_uri: masterAudio || null,
        character_ids: selectedChars,
      }),
    onSuccess: onCreated,
    onError: report,
  });

  const canSubmit = concept && styleTone && bucket && folder;

  const toggleChar = (c: Character) =>
    setSelectedChars((prev) =>
      prev.includes(c.id) ? prev.filter((x) => x !== c.id) : [...prev, c.id],
    );

  return (
    <section className="card">
      <h2>1 · Vision</h2>

      <label className="field">
        <span>Concept</span>
        <textarea
          rows={3}
          placeholder="e.g. Snape Dogg drops a gritty 90s trap diss track"
          value={concept}
          onChange={(e) => setConcept(e.target.value)}
        />
      </label>

      <label className="field">
        <span>Style / Tone</span>
        <input
          placeholder="gritty 90s music video, film grain, moody"
          value={styleTone}
          onChange={(e) => setStyleTone(e.target.value)}
        />
      </label>

      <div className="field">
        <span>GCS bucket → folder</span>
        <div className="row">
          <input
            placeholder="my-bucket"
            value={bucket}
            onChange={(e) => setBucket(e.target.value)}
          />
          <button
            type="button"
            onClick={() => {
              setBrowsedBucket(bucket);
              folders.refetch();
            }}
            disabled={!bucket}
          >
            Browse
          </button>
        </div>
        {folders.isFetching && <p className="muted">Loading folders…</p>}
        {folders.data && (
          <div className="folder-list">
            {folders.data.folders.map((f) => (
              <button
                key={f}
                type="button"
                className={`chip ${folder === f ? "selected" : ""}`}
                onClick={() => setFolder(f)}
              >
                {f}/
              </button>
            ))}
            <input
              className="chip-input"
              placeholder="or type a new folder"
              value={folder}
              onChange={(e) => setFolder(e.target.value)}
            />
          </div>
        )}
        {!folders.data && (
          <input
            placeholder="folder name"
            value={folder}
            onChange={(e) => setFolder(e.target.value)}
          />
        )}
      </div>

      <label className="field">
        <span>Master audio URI (optional)</span>
        <input
          placeholder="gs://my-bucket/proj/master.mp3"
          value={masterAudio}
          onChange={(e) => setMasterAudio(e.target.value)}
        />
      </label>

      <div className="field">
        <span>Characters (from library)</span>
        {characters.data && characters.data.length > 0 ? (
          <div className="folder-list">
            {characters.data.map((c) => (
              <button
                key={c.id}
                type="button"
                className={`chip ${selectedChars.includes(c.id) ? "selected" : ""}`}
                onClick={() => toggleChar(c)}
                title={c.physical_traits}
              >
                {c.name}
                {c.reference_uri ? " 📎" : ""}
              </button>
            ))}
          </div>
        ) : (
          <p className="muted">No saved characters yet.</p>
        )}
      </div>

      <button className="primary" onClick={() => create.mutate()} disabled={!canSubmit || create.isPending}>
        {create.isPending ? "Creating…" : "Create session →"}
      </button>
    </section>
  );
}
