import { useMutation } from "@tanstack/react-query";
import { api } from "../api";
import { useErrorReporter } from "../ErrorToast";
import type { Session } from "../types";

interface Props {
  session: Session;
}

export function FinalCutStage({ session }: Props) {
  const { report } = useErrorReporter();

  const assemble = useMutation({
    mutationFn: () => api.assemble(session.id),
    onError: report,
  });

  const approvedCount = session.shots.filter((s) => s.status === "approved").length;

  return (
    <section className="card">
      <h2>4 · Final Cut</h2>
      <p className="muted">
        Stitches {approvedCount} approved shot{approvedCount === 1 ? "" : "s"} with FFmpeg
        {session.master_audio_uri ? ", ducking the native bed under your master track." : "."}
      </p>

      <button className="primary" onClick={() => assemble.mutate()} disabled={assemble.isPending}>
        {assemble.isPending ? "Assembling…" : "Assemble final cut"}
      </button>

      {assemble.data && (
        <div className="final">
          <video src={assemble.data.signed_url} controls preload="metadata" />
          <p className="muted">
            {assemble.data.shot_count} shots · <code>{assemble.data.final_uri}</code>
          </p>
          <a className="primary as-link" href={assemble.data.signed_url} download>
            Download final_cut.mp4
          </a>
        </div>
      )}
    </section>
  );
}
