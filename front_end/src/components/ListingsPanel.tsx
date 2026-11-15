/**
 * The cards Tom found, shown beside the call: image, price, finish and a link to the eBay
 * listing. The card Tom recommends is highlighted.
 */
import type { Candidate } from "../types/search";
import type { ListingsState } from "../types/listings";

interface ListingsPanelProps {
  state: ListingsState;
  /** Name of the card Tom recommended, if he has named one. */
  tomsPick: string | null;
}

/** Format a price string from the backend ("3.99") as pounds. */
export function formatPrice(price: string | null): string {
  return price === null ? "Price on request" : `£${Number(price).toFixed(2)}`;
}

function ListingCard({ candidate, isPick }: { candidate: Candidate; isPick: boolean }) {
  return (
    <li className={`listing${isPick ? " listing--pick" : ""}`} aria-current={isPick || undefined}>
      {isPick && <span className="listing__badge">Tom's pick</span>}
      {candidate.image_url ? (
        <img className="listing__image" src={candidate.image_url} alt={candidate.name} loading="lazy" />
      ) : (
        <div className="listing__image listing__image--missing">No image</div>
      )}
      <div className="listing__body">
        <h3 className="listing__title">{candidate.title}</h3>
        <p className="listing__type">{candidate.type_line}</p>
        <p className="listing__price">{formatPrice(candidate.price)}</p>
        {candidate.other_finishes.length > 0 && (
          <p className="listing__also">
            Also in {candidate.other_finishes.map((finish) => finish.toLowerCase()).join(", ")}
          </p>
        )}
        <a
          className="listing__link"
          href={candidate.listing_url}
          target="_blank"
          rel="noopener noreferrer"
        >
          View on eBay
        </a>
      </div>
    </li>
  );
}

export function ListingsPanel({ state, tomsPick }: ListingsPanelProps) {
  return (
    <section className="listings" aria-label="Recommended listings" aria-live="polite">
      <h2 className="listings__heading">On the shelves</h2>

      {state.status === "idle" && (
        <p className="listings__message">
          Tell Tom about your deck and the cards he finds will appear here.
        </p>
      )}

      {state.status === "searching" && (
        <p className="listings__message">
          Searching for {state.request.role ? state.request.role.replace(/_/g, " ") : "cards"} for{" "}
          {state.request.commander}…
        </p>
      )}

      {state.status === "error" && (
        <p className="listings__message listings__message--error" role="alert">
          {state.message}
        </p>
      )}

      {state.status === "results" && (
        <>
          <p className="listings__summary">
            For <strong>{state.result.commander.name}</strong>
            {state.result.relaxed && " (nothing matched that exact role, so here are close alternatives)"}
          </p>
          {state.result.candidates.length === 0 ? (
            <p className="listings__message">Nothing suitable is in stock right now.</p>
          ) : (
            <ul className="listings__grid">
              {state.result.candidates.map((candidate) => (
                <ListingCard
                  key={candidate.listing_url}
                  candidate={candidate}
                  isPick={candidate.name === tomsPick}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}
