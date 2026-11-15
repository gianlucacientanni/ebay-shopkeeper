import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ListingsPanel, formatPrice } from "../../src/components/ListingsPanel";
import type { SearchResult } from "../../src/types/search";

const RESULT: SearchResult = {
  query: "(s:hob) id<=g otag:ramp",
  commander: { name: "Radagast the Brown", colour_identity: "G", type_line: "", oracle_text: "" },
  inspected: 10,
  in_stock_count: 2,
  relaxed: false,
  candidates: [
    {
      name: "Troop of Ponies",
      title: "Troop of Ponies (foil)",
      price: "3.99",
      finish: "FOIL",
      listing_url: "https://www.ebay.co.uk/itm/147540417740",
      image_url: "https://cards.scryfall.io/troop.jpg",
      type_line: "Creature — Horse",
      mana_cost: "{2}",
      oracle_text: "Vigilance",
      other_finishes: ["NONFOIL"],
    },
    {
      name: "Springleaf Drum",
      title: "Springleaf Drum",
      price: "1.99",
      finish: "NONFOIL",
      listing_url: "https://www.ebay.co.uk/itm/147228829890",
      image_url: null,
      type_line: "Artifact",
      mana_cost: "{1}",
      oracle_text: "",
      other_finishes: [],
    },
  ],
};

describe("ListingsPanel", () => {
  it("shows a prompt before any search", () => {
    render(<ListingsPanel state={{ status: "idle" }} tomsPick={null} />);
    expect(screen.getByText(/Tell Tom about your deck/)).toBeInTheDocument();
  });

  it("shows what's being searched for", () => {
    render(
      <ListingsPanel
        state={{ status: "searching", request: { commander: "Radagast the Brown", role: "card_draw" } }}
        tomsPick={null}
      />,
    );
    expect(screen.getByText(/Searching for card draw for Radagast the Brown/)).toBeInTheDocument();
  });

  it("shows errors as an alert", () => {
    render(<ListingsPanel state={{ status: "error", message: "The stock search failed" }} tomsPick={null} />);
    expect(screen.getByRole("alert")).toHaveTextContent("The stock search failed");
  });

  it("renders each listing with a safe eBay link", () => {
    render(<ListingsPanel state={{ status: "results", result: RESULT }} tomsPick={null} />);

    const links = screen.getAllByRole("link", { name: "View on eBay" });
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "https://www.ebay.co.uk/itm/147540417740",
      "https://www.ebay.co.uk/itm/147228829890",
    ]);
    for (const link of links) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
    expect(screen.getByText("£3.99")).toBeInTheDocument();
    expect(screen.getByText("Also in nonfoil")).toBeInTheDocument();
    expect(screen.getByText("No image")).toBeInTheDocument();
  });

  it("highlights Tom's pick", () => {
    render(<ListingsPanel state={{ status: "results", result: RESULT }} tomsPick="Springleaf Drum" />);
    expect(screen.getAllByText("Tom's pick")).toHaveLength(1);
    expect(screen.getByText("Tom's pick").closest("li")).toHaveTextContent("Springleaf Drum");
  });

  it("explains relaxed results and empty stock", () => {
    const empty = { ...RESULT, relaxed: true, candidates: [] };
    render(<ListingsPanel state={{ status: "results", result: empty }} tomsPick={null} />);
    expect(screen.getByText(/nothing matched that exact role/)).toBeInTheDocument();
    expect(screen.getByText("Nothing suitable is in stock right now.")).toBeInTheDocument();
  });
});

describe("formatPrice", () => {
  const testCases = [
    { description: "two decimals", price: "3.99", expected: "£3.99" },
    { description: "pads to two decimals", price: "2.5", expected: "£2.50" },
    { description: "unknown price", price: null, expected: "Price on request" },
  ];
  for (const testCase of testCases) {
    it(testCase.description, () => {
      expect(formatPrice(testCase.price)).toBe(testCase.expected);
    });
  }
});
