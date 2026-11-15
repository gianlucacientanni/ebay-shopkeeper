/** The shop's front door: a short intro and the button that starts a call with Tom. */

interface StartScreenProps {
  onStart: () => void;
  starting: boolean;
  /** Why the last attempt failed or the call ended, if it did. */
  notice: string | null;
  /** Id of the last call, so it can be reviewed with `uv run review-call <id>`. */
  lastConversationId?: string | null;
}

export function StartScreen({ onStart, starting, notice, lastConversationId }: StartScreenProps) {
  return (
    <section className="start">
      <h1 className="start__title">Arcanum Collectibles</h1>
      <p className="start__intro">
        Something not quite working in your Commander deck? Tell Tom what's going wrong and he'll
        find a card on our shelves to fix it.
      </p>
      <button type="button" className="start__button" onClick={onStart} disabled={starting}>
        {starting ? "Calling Tom…" : "Talk to Tom"}
      </button>
      {notice && (
        <p className="start__notice" role="status">
          {notice}
        </p>
      )}
      {lastConversationId && (
        <p className="start__review">
          Last call: <code>{lastConversationId}</code>. Review it with{" "}
          <code>uv run review-call {lastConversationId}</code>
        </p>
      )}
    </section>
  );
}
